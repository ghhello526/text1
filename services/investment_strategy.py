from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from datetime import date


class TradeType(Enum):
    """交易类型"""

    BUY = "买入"
    SELL = "卖出"
    INITIAL = "建仓"
    FINAL = "清仓"


@dataclass
class TradeRecord:
    """交易记录"""

    date: date
    trade_type: TradeType
    nav: float
    amount: float
    shares: float
    total_cost: float
    remaining_cash: float
    note: str = ""


@dataclass
class StrategyResult:
    """策略执行结果"""

    trades: list[TradeRecord]
    total_investment: float
    final_value: float
    total_return_rate: float
    buy_count: int
    sell_count: int
    remaining_shares: float
    remaining_cash: float
    start_date: date
    end_date: date
    buy_threshold: float
    sell_threshold: float


class InvestmentStrategy:
    """阶梯买卖投资策略（循环高抛低吸）

    投资规则：
    - 总资金可配置（默认1万元）
    - 初始建仓为总资金的25%
    - 买入触发：净值下跌达到设定比例，按连续阶梯比例买入当前现金（越跌越重仓）
    - 卖出触发：净值上涨达到设定比例，按比例减仓
    - 连续买入限制：最多连续买入N次后停止加仓
    - 连续卖出限制：最多连续卖出N次后停止减仓
    - 任意一次卖出后重置连续买入计数，可开启新一轮加仓（循环）
    - 任意一次买入后重置连续卖出计数
    """

    DEFAULT_TOTAL_CAPITAL = 10000.0
    INITIAL_INVESTMENT_RATIO = 0.25  # 初始建仓比例（总资金的25%）

    # 阶梯买入比例（基于当前现金，越跌比例越大）
    BUY_RATIOS = [0.10, 0.20, 0.30, 0.40, 0.50]
    # 卖出份额比例（基于当前持仓）
    SELL_RATIOS = [0.25, 0.25, 0.25, 0.25]

    def __init__(
        self,
        nav_data: pd.DataFrame,
        start_date: date,
        end_date: date,
        buy_threshold: float,
        sell_threshold: float,
        total_capital: float = None,
        max_consecutive_buy: int = 5,
        max_consecutive_sell: int = 5,
        buy_ratios: list[float] | None = None,
    ) -> None:
        """初始化投资策略

        Args:
            nav_data: 基金净值数据，包含 '净值日期' 和 'unit_nav' 列
            start_date: 建仓日期
            end_date: 清仓日期
            buy_threshold: 下跌买入比例（如 0.05 表示 5%）
            sell_threshold: 上涨卖出比例（如 0.05 表示 5%）
            total_capital: 总资金（默认10000元）
            max_consecutive_buy: 最多连续买入次数（卖出后重置，可再次买入）
            max_consecutive_sell: 最多连续卖出次数（买入后重置，可再次卖出）
            buy_ratios: 阶梯买入比例列表（基于当前现金），默认 [0.10, 0.20, 0.30, 0.40, 0.50]
        """
        self.nav_data = nav_data.copy()
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.total_capital = total_capital or self.DEFAULT_TOTAL_CAPITAL
        self.max_consecutive_buy = max_consecutive_buy
        self.max_consecutive_sell = max_consecutive_sell
        self.buy_ratios = buy_ratios if buy_ratios is not None else self.BUY_RATIOS

        # 计算初始建仓金额
        self.initial_investment = self.total_capital * self.INITIAL_INVESTMENT_RATIO

        # 确保数据类型正确
        self.nav_data["净值日期"] = pd.to_datetime(self.nav_data["净值日期"])
        self.nav_data = self.nav_data.sort_values("净值日期").reset_index(drop=True)

        # 筛选指定日期范围内的数据
        mask = (self.nav_data["净值日期"] >= self.start_date) & (
            self.nav_data["净值日期"] <= self.end_date
        )
        self.period_data = self.nav_data[mask].copy()

        if self.period_data.empty:
            raise ValueError("指定日期范围内没有净值数据")

    def execute(self) -> StrategyResult:
        """执行投资策略，返回结果

        循环规则：
        - 连续下跌最多买入N次后停止加仓；任意一次卖出后重置买入计数，开启新一轮
        - 连续上涨最多卖出N次后停止减仓；任意一次买入后重置卖出计数
        - 买入金额按阶梯动态计算：第k次连续买入使用 buy_ratios[k-1] × 当前现金
        """
        trades: list[TradeRecord] = []

        cash = self.total_capital
        shares = 0.0
        buy_count = 0  # 统计：总买入次数
        sell_count = 0  # 统计：总卖出次数
        consecutive_buy_count = 0  # 当前连续买入次数（卖出后归零）
        consecutive_sell_count = 0  # 当前连续卖出次数（买入后归零）
        reference_nav = None

        # 1. 在建仓日期买入初始金额
        initial_row = self.period_data.iloc[0]
        initial_nav = float(initial_row["unit_nav"])
        initial_shares = self.initial_investment / initial_nav
        shares += initial_shares
        cash -= self.initial_investment
        reference_nav = initial_nav
        # 建仓不计入连续买入计数，保持为0，确保首次条件买入使用 buy_ratios[0]

        trades.append(
            TradeRecord(
                date=initial_row["净值日期"].date(),
                trade_type=TradeType.INITIAL,
                nav=initial_nav,
                amount=self.initial_investment,
                shares=initial_shares,
                total_cost=self.initial_investment,
                remaining_cash=cash,
                note=f"初始建仓，参考净值: {initial_nav:.4f}",
            )
        )

        # 2. 遍历建仓日期到清仓日期之间的每个交易日（跳过第一天）
        for idx in range(1, len(self.period_data) - 1):
            row = self.period_data.iloc[idx]
            current_nav = float(row["unit_nav"])
            current_date = row["净值日期"].date()

            # 计算本次买入金额（基于当前现金的阶梯比例）
            ratio_idx = min(consecutive_buy_count, len(self.buy_ratios) - 1)
            buy_amount = cash * self.buy_ratios[ratio_idx]

            can_buy = (
                current_nav <= reference_nav * (1 - self.buy_threshold)
                and cash > 0
                and buy_amount > 0
                and consecutive_buy_count < self.max_consecutive_buy
            )

            if can_buy:
                buy_shares = buy_amount / current_nav
                shares += buy_shares
                cash -= buy_amount
                buy_count += 1
                consecutive_buy_count += 1
                consecutive_sell_count = 0  # 买入后重置连续卖出计数
                reference_nav = current_nav

                trades.append(
                    TradeRecord(
                        date=current_date,
                        trade_type=TradeType.BUY,
                        nav=current_nav,
                        amount=buy_amount,
                        shares=buy_shares,
                        total_cost=sum(
                            t.amount for t in trades if t.trade_type != TradeType.SELL
                        ),
                        remaining_cash=cash,
                        note=(
                            f"第{buy_count}次买入(连续第{consecutive_buy_count}次，"
                            f"用{self.buy_ratios[ratio_idx]*100:.0f}%现金)，"
                            f"触发下跌 {self.buy_threshold*100:.1f}%"
                        ),
                    )
                )
                continue  # 买入后跳过当天卖出判断

            # 卖出判断
            sell_ratio_idx = min(consecutive_sell_count, len(self.SELL_RATIOS) - 1)
            sell_ratio = self.SELL_RATIOS[sell_ratio_idx]

            can_sell = (
                shares > 0
                and current_nav >= reference_nav * (1 + self.sell_threshold)
                and consecutive_sell_count < self.max_consecutive_sell
            )

            if can_sell:
                sell_shares = shares * sell_ratio
                sell_amount = sell_shares * current_nav
                shares -= sell_shares
                cash += sell_amount
                sell_count += 1
                consecutive_sell_count += 1
                consecutive_buy_count = 0  # 卖出后重置连续买入计数（开启新一轮）
                reference_nav = current_nav

                trades.append(
                    TradeRecord(
                        date=current_date,
                        trade_type=TradeType.SELL,
                        nav=current_nav,
                        amount=sell_amount,
                        shares=sell_shares,
                        total_cost=sum(
                            t.amount for t in trades if t.trade_type != TradeType.SELL
                        ),
                        remaining_cash=cash,
                        note=(
                            f"第{sell_count}次卖出(连续第{consecutive_sell_count}次，"
                            f"减仓{sell_ratio*100:.0f}%持仓)，"
                            f"触发上涨 {self.sell_threshold*100:.1f}%"
                        ),
                    )
                )

        # 3. 在清仓日期卖出所有剩余持仓
        final_row = self.period_data.iloc[-1]
        final_nav = float(final_row["unit_nav"])
        final_date = final_row["净值日期"].date()

        if shares > 0:
            sell_amount = shares * final_nav
            cash += sell_amount

            trades.append(
                TradeRecord(
                    date=final_date,
                    trade_type=TradeType.FINAL,
                    nav=final_nav,
                    amount=sell_amount,
                    shares=shares,
                    total_cost=sum(
                        t.amount for t in trades if t.trade_type != TradeType.SELL
                    ),
                    remaining_cash=cash,
                    note="清仓卖出所有剩余份额",
                )
            )
            shares = 0.0

        # 4. 计算最终收益率
        final_value = cash
        total_return_rate = (final_value - self.total_capital) / self.total_capital

        return StrategyResult(
            trades=trades,
            total_investment=self.total_capital,
            final_value=final_value,
            total_return_rate=total_return_rate,
            buy_count=buy_count,
            sell_count=sell_count,
            remaining_shares=shares,
            remaining_cash=cash,
            start_date=self.start_date.date(),
            end_date=self.end_date.date(),
            buy_threshold=self.buy_threshold,
            sell_threshold=self.sell_threshold,
        )


def format_strategy_result(result: StrategyResult) -> str:
    """格式化策略结果为可读字符串"""
    lines = [
        "=" * 50,
        "投资策略执行结果",
        "=" * 50,
        f"投资区间: {result.start_date} 至 {result.end_date}",
        f"总资金: {result.total_investment:.2f} 元",
        f"买入阈值: {result.buy_threshold*100:.1f}% (下跌触发)",
        f"卖出阈值: {result.sell_threshold*100:.1f}% (上涨触发)",
        "-" * 50,
        f"最终金额: {result.final_value:.2f} 元",
        f"总收益率: {result.total_return_rate*100:+.2f}%",
        f"买入次数: {result.buy_count} 次",
        f"卖出次数: {result.sell_count} 次",
        f"剩余现金: {result.remaining_cash:.2f} 元",
        "-" * 50,
        "交易明细:",
    ]

    for trade in result.trades:
        if trade.trade_type == TradeType.BUY:
            lines.append(
                f"  [{trade.date}] 买入 {trade.amount:.2f}元 @ {trade.nav:.4f} "
                f"({trade.note})"
            )
        elif trade.trade_type == TradeType.SELL:
            lines.append(
                f"  [{trade.date}] 卖出 {trade.amount:.2f}元 @ {trade.nav:.4f} "
                f"({trade.note})"
            )
        elif trade.trade_type == TradeType.INITIAL:
            lines.append(
                f"  [{trade.date}] 建仓 {trade.amount:.2f}元 @ {trade.nav:.4f} "
                f"({trade.note})"
            )
        elif trade.trade_type == TradeType.FINAL:
            lines.append(
                f"  [{trade.date}] 清仓 {trade.amount:.2f}元 @ {trade.nav:.4f} "
                f"({trade.note})"
            )

    lines.append("=" * 50)
    return "\n".join(lines)
