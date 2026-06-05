"""三策略引擎 — 建仓/波动/止盈策略核心逻辑"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from services.models import (
    BacktestResult,
    BacktestTrade,
    Fund,
    Position,
    SignalAction,
    SignalUrgency,
    StrategyType,
    TradeType,
    TradingSignal,
    Zone,
)

# 默认阈值
DEFAULT_THRESHOLD = 0.05  # 5%
MAX_POSITION_BUILD = 0.70  # 建仓策略最大仓位70%
MAX_POSITION_SWING = 0.50  # 波动策略最大仓位50%
MAX_POSITION_TAKE_PROFIT = 0.30  # 止盈时目标仓位30%
MIN_POSITION_BUBBLE = 0.10  # 泡沫区最大仓位10%
DRAWDOWN_CLEAR_THRESHOLD = 0.05  # 回撤5%清仓


class StrategyEngine:
    """三策略引擎

    根据当前净值 vs 三线位置判定策略，并生成交易信号或执行回测。
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD) -> None:
        """
        Args:
            threshold: 买卖触发阈值，默认5%
        """
        self.threshold = threshold

    # ==================== 实时信号生成 ====================

    def evaluate_signal(
        self,
        nav: float,
        fund: Fund,
        position: Position,
    ) -> TradingSignal:
        """根据当前净值、基金配置和持仓状态，生成交易信号。

        Args:
            nav: 当前最新净值
            fund: 基金配置（含三线）
            position: 当前持仓状态
        Returns:
            TradingSignal
        """
        # 如果三线未设定，返回持有信号
        if not fund.opportunity_line or not fund.middle_line or not fund.danger_line:
            return TradingSignal(
                action=SignalAction.HOLD,
                urgency=SignalUrgency.LOW,
                strategy=StrategyType.NONE,
                trigger_reason="三线估值未设定，无法生成信号",
                current_nav=nav,
                zone=Zone.FAIR,
            )

        zone = self._determine_zone(nav, fund)
        strategy = self._zone_to_strategy(zone)

        # 计算当前仓位百分比
        total_capital = fund.per_share_amount * fund.total_shares_count
        current_value = position.total_shares * nav
        position_pct = current_value / total_capital if total_capital > 0 else 0.0

        # 无锚点（未建仓）
        if position.anchor_nav is None or position.total_shares == 0:
            return TradingSignal(
                action=SignalAction.BUY,
                urgency=SignalUrgency.HIGH,
                strategy=strategy,
                suggested_amount=fund.per_share_amount,
                suggested_shares=fund.per_share_amount / nav if nav > 0 else 0,
                trigger_reason="尚未建仓，建议首次买入",
                next_trigger_up=0.0,
                next_trigger_down=0.0,
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=0.0,
            )

        anchor = position.anchor_nav
        change_pct = (nav - anchor) / anchor if anchor > 0 else 0.0

        # 根据策略类型判断信号
        if strategy == StrategyType.BUILD:
            return self._evaluate_build(nav, fund, position, zone, position_pct, change_pct)
        elif strategy == StrategyType.SWING:
            return self._evaluate_swing(nav, fund, position, zone, position_pct, change_pct)
        else:
            return self._evaluate_take_profit(nav, fund, position, zone, position_pct, change_pct)

    def _evaluate_build(
        self, nav: float, fund: Fund, position: Position,
        zone: Zone, position_pct: float, change_pct: float,
    ) -> TradingSignal:
        """建仓策略信号：只买不卖"""
        anchor = position.anchor_nav or nav
        next_down = anchor * (1 - self.threshold)
        next_up = anchor * (1 + self.threshold)

        # 仓位已满
        if position_pct >= MAX_POSITION_BUILD:
            return TradingSignal(
                action=SignalAction.HOLD,
                urgency=SignalUrgency.LOW,
                strategy=StrategyType.BUILD,
                trigger_reason=f"建仓仓位已达上限 {position_pct*100:.1f}%≥70%，暂停操作",
                next_trigger_up=next_up,
                next_trigger_down=next_down,
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=anchor,
            )

        # 触发买入
        if change_pct <= -self.threshold:
            return TradingSignal(
                action=SignalAction.BUY,
                urgency=SignalUrgency.HIGH,
                strategy=StrategyType.BUILD,
                suggested_amount=fund.per_share_amount,
                suggested_shares=fund.per_share_amount / nav if nav > 0 else 0,
                trigger_reason=f"净值从锚点{anchor:.4f}下跌{abs(change_pct)*100:.1f}%，触发建仓买入",
                next_trigger_up=nav * (1 + self.threshold),
                next_trigger_down=nav * (1 - self.threshold),
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=anchor,
            )

        # 未触发
        return TradingSignal(
            action=SignalAction.HOLD,
            urgency=SignalUrgency.LOW,
            strategy=StrategyType.BUILD,
            trigger_reason=f"建仓策略等待中，当前跌幅{abs(change_pct)*100:.1f}%，需达{self.threshold*100:.0f}%",
            next_trigger_up=next_up,
            next_trigger_down=next_down,
            position_pct=position_pct,
            zone=zone,
            current_nav=nav,
            anchor_nav=anchor,
        )

    def _evaluate_swing(
        self, nav: float, fund: Fund, position: Position,
        zone: Zone, position_pct: float, change_pct: float,
    ) -> TradingSignal:
        """波动策略信号：低买高卖"""
        anchor = position.anchor_nav or nav
        next_down = anchor * (1 - self.threshold)
        next_up = anchor * (1 + self.threshold)

        # 上涨触发卖出
        if change_pct >= self.threshold and position.total_shares > 0:
            sell_shares = min(
                position.swing_shares,
                fund.per_share_amount / nav if nav > 0 else 0,
            )
            sell_amount = sell_shares * nav
            return TradingSignal(
                action=SignalAction.SELL,
                urgency=SignalUrgency.HIGH,
                strategy=StrategyType.SWING,
                suggested_amount=sell_amount,
                suggested_shares=sell_shares,
                trigger_reason=f"净值从锚点{anchor:.4f}上涨{change_pct*100:.1f}%，触发波动卖出",
                next_trigger_up=nav * (1 + self.threshold),
                next_trigger_down=nav * (1 - self.threshold),
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=anchor,
            )

        # 下跌触发买入
        if change_pct <= -self.threshold:
            return TradingSignal(
                action=SignalAction.BUY,
                urgency=SignalUrgency.HIGH,
                strategy=StrategyType.SWING,
                suggested_amount=fund.per_share_amount,
                suggested_shares=fund.per_share_amount / nav if nav > 0 else 0,
                trigger_reason=f"净值从锚点{anchor:.4f}下跌{abs(change_pct)*100:.1f}%，触发波动买入",
                next_trigger_up=nav * (1 + self.threshold),
                next_trigger_down=nav * (1 - self.threshold),
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=anchor,
            )

        # 未触发
        return TradingSignal(
            action=SignalAction.HOLD,
            urgency=SignalUrgency.LOW,
            strategy=StrategyType.SWING,
            trigger_reason=f"波动策略等待中，当前变动{change_pct*100:+.1f}%，阈值±{self.threshold*100:.0f}%",
            next_trigger_up=next_up,
            next_trigger_down=next_down,
            position_pct=position_pct,
            zone=zone,
            current_nav=nav,
            anchor_nav=anchor,
        )

    def _evaluate_take_profit(
        self, nav: float, fund: Fund, position: Position,
        zone: Zone, position_pct: float, change_pct: float,
    ) -> TradingSignal:
        """止盈策略信号：分批减仓"""
        anchor = position.anchor_nav or nav
        highest = position.highest_nav or nav

        # 更新最高净值
        if nav > highest:
            highest = nav

        # 判断回撤清仓（泡沫区，从最高点回撤5%）
        if zone == Zone.BUBBLE and highest > 0:
            drawdown = (highest - nav) / highest
            if drawdown >= DRAWDOWN_CLEAR_THRESHOLD and position.total_shares > 0:
                sell_amount = position.total_shares * nav
                return TradingSignal(
                    action=SignalAction.SELL,
                    urgency=SignalUrgency.HIGH,
                    strategy=StrategyType.TAKE_PROFIT,
                    suggested_amount=sell_amount,
                    suggested_shares=position.total_shares,
                    trigger_reason=f"从高点{highest:.4f}回撤{drawdown*100:.1f}%≥5%，触发全部清仓",
                    next_trigger_up=0.0,
                    next_trigger_down=0.0,
                    position_pct=position_pct,
                    zone=zone,
                    current_nav=nav,
                    anchor_nav=anchor,
                )

        # 仓位高于目标，建议减仓
        target_pct = MIN_POSITION_BUBBLE if zone == Zone.BUBBLE else MAX_POSITION_TAKE_PROFIT
        if position_pct > target_pct and position.total_shares > 0:
            # 每次卖出1份
            sell_shares = min(
                position.total_shares,
                fund.per_share_amount / nav if nav > 0 else 0,
            )
            sell_amount = sell_shares * nav
            return TradingSignal(
                action=SignalAction.SELL,
                urgency=SignalUrgency.MEDIUM,
                strategy=StrategyType.TAKE_PROFIT,
                suggested_amount=sell_amount,
                suggested_shares=sell_shares,
                trigger_reason=f"止盈策略：当前仓位{position_pct*100:.1f}%＞目标{target_pct*100:.0f}%，建议减仓",
                next_trigger_up=nav * (1 + self.threshold),
                next_trigger_down=nav * (1 - self.threshold),
                position_pct=position_pct,
                zone=zone,
                current_nav=nav,
                anchor_nav=anchor,
            )

        # 未触发
        return TradingSignal(
            action=SignalAction.HOLD,
            urgency=SignalUrgency.LOW,
            strategy=StrategyType.TAKE_PROFIT,
            trigger_reason=f"止盈区间持有中，仓位{position_pct*100:.1f}%≤目标{target_pct*100:.0f}%",
            next_trigger_up=nav * (1 + self.threshold),
            next_trigger_down=nav * (1 - self.threshold),
            position_pct=position_pct,
            zone=zone,
            current_nav=nav,
            anchor_nav=anchor,
        )

    # ==================== 回测模式 ====================

    def backtest(
        self,
        nav_series: pd.DataFrame,
        fund: Fund,
        start_date: date,
        end_date: date,
    ) -> BacktestResult:
        """执行三策略回测。

        Args:
            nav_series: 净值数据，包含 '净值日期' 和 'unit_nav' 列
            fund: 基金配置（含三线设定）
            start_date: 回测起始日期
            end_date: 回测结束日期
        Returns:
            BacktestResult
        """
        df = nav_series.copy()
        df["净值日期"] = pd.to_datetime(df["净值日期"])
        df = df.sort_values("净值日期").reset_index(drop=True)

        # 筛选日期范围
        mask = (df["净值日期"].dt.date >= start_date) & (df["净值日期"].dt.date <= end_date)
        period = df[mask].copy()

        if period.empty:
            raise ValueError("指定日期范围内没有净值数据")

        # 回测状态
        total_capital = fund.per_share_amount * fund.total_shares_count
        cash = total_capital
        main_shares = 0.0
        swing_shares = 0.0
        anchor_nav: float | None = None
        highest_nav: float = 0.0
        consecutive_buy = 0
        consecutive_sell = 0

        trades: list[BacktestTrade] = []
        peak_value = total_capital  # 用于计算最大回撤
        max_drawdown = 0.0

        for idx, row in period.iterrows():
            nav = float(row["unit_nav"])
            current_date = row["净值日期"].date()
            total_shares = main_shares + swing_shares
            current_value = total_shares * nav + cash
            position_pct = (total_shares * nav) / total_capital if total_capital > 0 else 0.0

            # 更新最大回撤
            if current_value > peak_value:
                peak_value = current_value
            dd = (peak_value - current_value) / peak_value if peak_value > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

            # 更新最高净值
            if nav > highest_nav:
                highest_nav = nav

            # 判定区间和策略
            zone = self._determine_zone(nav, fund)
            strategy = self._zone_to_strategy(zone)

            # 未建仓时，首次买入
            if anchor_nav is None:
                buy_amount = fund.per_share_amount
                if cash >= buy_amount and buy_amount > 0:
                    buy_shares = buy_amount / nav
                    main_shares += buy_shares * fund.main_ratio
                    swing_shares += buy_shares * fund.swing_ratio
                    cash -= buy_amount
                    anchor_nav = nav
                    highest_nav = nav
                    trades.append(BacktestTrade(
                        trade_date=current_date,
                        trade_type=TradeType.INITIAL,
                        strategy_type=strategy,
                        nav=nav,
                        amount=buy_amount,
                        shares=buy_shares,
                        trigger_reason="首次建仓",
                        position_pct=(main_shares + swing_shares) * nav / total_capital,
                        total_value=(main_shares + swing_shares) * nav + cash,
                    ))
                continue

            change_pct = (nav - anchor_nav) / anchor_nav if anchor_nav > 0 else 0.0

            # 执行策略逻辑
            if strategy == StrategyType.BUILD:
                # 建仓策略：只买不卖
                if change_pct <= -self.threshold and position_pct < MAX_POSITION_BUILD:
                    buy_amount = min(fund.per_share_amount, cash)
                    if buy_amount > 0:
                        buy_shares = buy_amount / nav
                        main_shares += buy_shares * fund.main_ratio
                        swing_shares += buy_shares * fund.swing_ratio
                        cash -= buy_amount
                        anchor_nav = nav
                        consecutive_buy += 1
                        consecutive_sell = 0
                        trades.append(BacktestTrade(
                            trade_date=current_date,
                            trade_type=TradeType.BUY,
                            strategy_type=StrategyType.BUILD,
                            nav=nav,
                            amount=buy_amount,
                            shares=buy_shares,
                            trigger_reason=f"建仓买入：跌幅{abs(change_pct)*100:.1f}%",
                            position_pct=(main_shares + swing_shares) * nav / total_capital,
                            total_value=(main_shares + swing_shares) * nav + cash,
                        ))

            elif strategy == StrategyType.SWING:
                # 波动策略：低买高卖
                if change_pct >= self.threshold and swing_shares > 0:
                    # 卖出波动仓
                    sell_shares = min(swing_shares, fund.per_share_amount / nav)
                    sell_amount = sell_shares * nav
                    swing_shares -= sell_shares
                    cash += sell_amount
                    anchor_nav = nav
                    consecutive_sell += 1
                    consecutive_buy = 0
                    trades.append(BacktestTrade(
                        trade_date=current_date,
                        trade_type=TradeType.SELL,
                        strategy_type=StrategyType.SWING,
                        nav=nav,
                        amount=sell_amount,
                        shares=sell_shares,
                        trigger_reason=f"波动卖出：涨幅{change_pct*100:.1f}%",
                        position_pct=(main_shares + swing_shares) * nav / total_capital,
                        total_value=(main_shares + swing_shares) * nav + cash,
                    ))
                elif change_pct <= -self.threshold and position_pct < MAX_POSITION_SWING:
                    buy_amount = min(fund.per_share_amount, cash)
                    if buy_amount > 0:
                        buy_shares = buy_amount / nav
                        main_shares += buy_shares * fund.main_ratio
                        swing_shares += buy_shares * fund.swing_ratio
                        cash -= buy_amount
                        anchor_nav = nav
                        consecutive_buy += 1
                        consecutive_sell = 0
                        trades.append(BacktestTrade(
                            trade_date=current_date,
                            trade_type=TradeType.BUY,
                            strategy_type=StrategyType.SWING,
                            nav=nav,
                            amount=buy_amount,
                            shares=buy_shares,
                            trigger_reason=f"波动买入：跌幅{abs(change_pct)*100:.1f}%",
                            position_pct=(main_shares + swing_shares) * nav / total_capital,
                            total_value=(main_shares + swing_shares) * nav + cash,
                        ))

            else:
                # 止盈策略
                total_shares = main_shares + swing_shares
                # 泡沫区回撤清仓
                if zone == Zone.BUBBLE and highest_nav > 0:
                    drawdown = (highest_nav - nav) / highest_nav
                    if drawdown >= DRAWDOWN_CLEAR_THRESHOLD and total_shares > 0:
                        sell_amount = total_shares * nav
                        trades.append(BacktestTrade(
                            trade_date=current_date,
                            trade_type=TradeType.FINAL,
                            strategy_type=StrategyType.TAKE_PROFIT,
                            nav=nav,
                            amount=sell_amount,
                            shares=total_shares,
                            trigger_reason=f"回撤清仓：从高点回撤{drawdown*100:.1f}%",
                            position_pct=0.0,
                            total_value=cash + sell_amount,
                        ))
                        cash += sell_amount
                        main_shares = 0.0
                        swing_shares = 0.0
                        anchor_nav = None
                        highest_nav = 0.0
                        continue

                # 分批减仓
                target_pct = MIN_POSITION_BUBBLE if zone == Zone.BUBBLE else MAX_POSITION_TAKE_PROFIT
                if position_pct > target_pct and total_shares > 0:
                    sell_shares = min(total_shares, fund.per_share_amount / nav)
                    sell_amount = sell_shares * nav
                    # 优先卖出波动仓
                    if swing_shares >= sell_shares:
                        swing_shares -= sell_shares
                    else:
                        remaining = sell_shares - swing_shares
                        swing_shares = 0.0
                        main_shares -= remaining
                    cash += sell_amount
                    anchor_nav = nav
                    consecutive_sell += 1
                    consecutive_buy = 0
                    trades.append(BacktestTrade(
                        trade_date=current_date,
                        trade_type=TradeType.TAKE_PROFIT,
                        strategy_type=StrategyType.TAKE_PROFIT,
                        nav=nav,
                        amount=sell_amount,
                        shares=sell_shares,
                        trigger_reason=f"止盈减仓：仓位{position_pct*100:.1f}%＞{target_pct*100:.0f}%",
                        position_pct=(main_shares + swing_shares) * nav / total_capital,
                        total_value=(main_shares + swing_shares) * nav + cash,
                    ))

        # 计算最终结果
        total_shares = main_shares + swing_shares
        final_value = total_shares * float(period.iloc[-1]["unit_nav"]) + cash
        total_invested = total_capital - cash + (total_shares * float(period.iloc[-1]["unit_nav"]))
        total_return_rate = (final_value - total_capital) / total_capital

        buy_count = sum(1 for t in trades if t.trade_type in (TradeType.BUY, TradeType.INITIAL))
        sell_count = sum(1 for t in trades if t.trade_type in (TradeType.SELL, TradeType.TAKE_PROFIT, TradeType.FINAL))
        build_count = sum(1 for t in trades if t.strategy_type == StrategyType.BUILD)
        swing_count = sum(1 for t in trades if t.strategy_type == StrategyType.SWING)
        tp_count = sum(1 for t in trades if t.strategy_type == StrategyType.TAKE_PROFIT)

        return BacktestResult(
            trades=trades,
            total_investment=total_capital,
            final_value=final_value,
            total_return_rate=total_return_rate,
            max_drawdown=max_drawdown,
            buy_count=buy_count,
            sell_count=sell_count,
            build_count=build_count,
            swing_count=swing_count,
            take_profit_count=tp_count,
            start_date=start_date,
            end_date=end_date,
        )

    # ==================== 辅助方法 ====================

    @staticmethod
    def _determine_zone(nav: float, fund: Fund) -> Zone:
        """根据净值和三线位置判定区间。"""
        if fund.opportunity_line and nav <= fund.opportunity_line:
            return Zone.UNDERVALUED
        elif fund.middle_line and nav <= fund.middle_line:
            return Zone.FAIR
        elif fund.danger_line and nav <= fund.danger_line:
            return Zone.OVERVALUED
        else:
            return Zone.BUBBLE

    @staticmethod
    def _zone_to_strategy(zone: Zone) -> StrategyType:
        """区间到策略类型的映射。"""
        if zone == Zone.UNDERVALUED:
            return StrategyType.BUILD
        elif zone == Zone.FAIR:
            return StrategyType.SWING
        else:
            return StrategyType.TAKE_PROFIT
