"""实时信号生成器 — 封装从数据获取到信号输出的完整流程"""

from __future__ import annotations

from typing import TYPE_CHECKING

from services.database import DatabaseManager
from services.fund_service import FundDataError, FundService
from services.models import Fund, Position, SignalAction, SignalUrgency, StrategyType, TradingSignal, Zone
from services.strategy_engine import StrategyEngine

if TYPE_CHECKING:
    pass


class SignalGenerator:
    """实时信号生成器

    负责：
    1. 从数据库读取 Fund 和 Position
    2. 调用 FundService 获取最新净值
    3. 调用 StrategyEngine 生成交易信号
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        fund_service: FundService | None = None,
        engine: StrategyEngine | None = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.fund_service = fund_service or FundService()
        self.engine = engine or StrategyEngine()

    def generate_signal(self, fund_id: int) -> TradingSignal:
        """为指定基金生成交易信号。

        Args:
            fund_id: 基金 id
        Returns:
            TradingSignal
        Raises:
            ValueError: 基金不存在
            FundDataError: 净值获取失败
        """
        fund = self.db.get_fund(fund_id)
        if fund is None:
            raise ValueError(f"基金 id={fund_id} 不存在")

        position = self.db.get_position(fund_id)
        if position is None:
            position = Position(fund_id=fund_id)

        # 获取最新净值
        nav = self._get_latest_nav(fund.code)
        if nav is None:
            return TradingSignal(
                action=SignalAction.HOLD,
                urgency=SignalUrgency.LOW,
                strategy=StrategyType.NONE,
                trigger_reason="无法获取最新净值",
                zone=Zone.FAIR,
            )

        # 更新 highest_nav
        if position.highest_nav is not None and nav > position.highest_nav:
            position.highest_nav = nav
            self.db.update_position(position)
        elif position.highest_nav is None and position.total_shares > 0:
            position.highest_nav = nav
            self.db.update_position(position)

        # 生成信号
        signal = self.engine.evaluate_signal(nav, fund, position)
        return signal

    def refresh_all_signals(self) -> dict[int, TradingSignal]:
        """刷新所有基金的交易信号。

        Returns:
            dict[fund_id, TradingSignal]
        """
        funds = self.db.get_all_funds()
        signals: dict[int, TradingSignal] = {}

        for fund in funds:
            try:
                signal = self.generate_signal(fund.id)
                signals[fund.id] = signal
            except Exception:
                # 获取失败时返回默认持有信号
                signals[fund.id] = TradingSignal(
                    action=SignalAction.HOLD,
                    urgency=SignalUrgency.LOW,
                    strategy=StrategyType.NONE,
                    trigger_reason="信号生成失败",
                    zone=Zone.FAIR,
                )

        return signals

    def confirm_trade(
        self,
        fund_id: int,
        signal: TradingSignal,
        actual_nav: float | None = None,
        actual_amount: float | None = None,
    ) -> None:
        """确认执行交易，更新持仓状态和交易记录。

        Args:
            fund_id: 基金 id
            signal: 当前信号
            actual_nav: 实际成交净值（默认使用信号中的净值）
            actual_amount: 实际成交金额（默认使用信号建议金额）
        """
        from datetime import date as date_type

        from services.models import Trade

        fund = self.db.get_fund(fund_id)
        if fund is None:
            raise ValueError(f"基金 id={fund_id} 不存在")

        position = self.db.get_position(fund_id)
        if position is None:
            position = Position(fund_id=fund_id)

        nav = actual_nav or signal.current_nav
        amount = actual_amount or signal.suggested_amount

        if nav <= 0 or amount <= 0:
            return

        shares = amount / nav
        today = date_type.today().isoformat()

        if signal.action == SignalAction.BUY:
            # 买入：增加持仓
            buy_main = shares * fund.main_ratio
            buy_swing = shares * fund.swing_ratio
            position.main_shares += buy_main
            position.swing_shares += buy_swing
            position.total_shares = position.main_shares + position.swing_shares
            position.total_invested += amount
            position.anchor_nav = nav
            position.highest_nav = nav
            position.consecutive_buy += 1
            position.consecutive_sell = 0
            position.current_strategy = signal.strategy.value

            trade_type = "建仓" if position.total_invested == amount else "买入"

        elif signal.action == SignalAction.SELL:
            # 卖出：减少持仓
            if position.swing_shares >= shares:
                position.swing_shares -= shares
            else:
                remaining = shares - position.swing_shares
                position.swing_shares = 0.0
                position.main_shares = max(0.0, position.main_shares - remaining)

            position.total_shares = position.main_shares + position.swing_shares
            position.anchor_nav = nav
            position.consecutive_sell += 1
            position.consecutive_buy = 0
            position.current_strategy = signal.strategy.value

            if position.total_shares <= 0:
                trade_type = "清仓"
                position.anchor_nav = None
                position.highest_nav = None
            elif signal.strategy == StrategyType.TAKE_PROFIT:
                trade_type = "止盈"
            else:
                trade_type = "卖出"
        else:
            return  # hold 不记录

        # 更新持仓
        self.db.update_position(position)

        # 写入交易记录
        trade = Trade(
            fund_id=fund_id,
            trade_date=today,
            trade_type=trade_type,
            strategy_type=signal.strategy.value,
            nav=nav,
            amount=amount,
            shares=shares,
            trigger_reason=signal.trigger_reason,
            confirmed=1,
        )
        self.db.add_trade(trade)

    def _get_latest_nav(self, code: str) -> float | None:
        """获取基金最新净值。"""
        try:
            history = self.fund_service.get_fund_history(code)
            if history.dataframe.empty:
                return None
            # 取最新一条
            latest = history.dataframe.iloc[-1]
            return float(latest["unit_nav"])
        except (FundDataError, Exception):
            return None
