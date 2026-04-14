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
    """阶梯买卖投资策略

    投资规则：
    - 单支基金，总计 2 万元
    - 初始建仓 5000 元
    - 剩余 15000 元分阶梯买卖
    - 买入：最多 5 次，阶梯金额：2000, 2500, 3000, 3500, 4000（均值 3000）
    - 卖出：最多 3 次，阶梯金额：3000, 4000, 5000（均值 4000）
    - 买入触发：净值下跌达到设定比例
    - 卖出触发：净值上涨达到设定比例
    """

    TOTAL_CAPITAL = 20000.0
    INITIAL_INVESTMENT = 5000.0

    # 阶梯买入金额（元），共5次，均值3000
    BUY_AMOUNTS = [2000, 2500, 3000, 3500, 4000]

    # 阶梯卖出金额（元），共3次，均值4000
    SELL_AMOUNTS = [3000, 4000, 5000]

    MAX_BUY_COUNT = 5
    MAX_SELL_COUNT = 3

    def __init__(
        self,
        nav_data: pd.DataFrame,
        start_date: date,
        end_date: date,
        buy_threshold: float,
        sell_threshold: float,
    ) -> None:
        """初始化投资策略

        Args:
            nav_data: 基金净值数据，包含 '净值日期' 和 'unit_nav' 列
            start_date: 建仓日期
            end_date: 清仓日期
            buy_threshold: 下跌买入比例（如 0.05 表示 5%）
            sell_threshold: 上涨卖出比例（如 0.05 表示 5%）
        """
        self.nav_data = nav_data.copy()
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

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
        """执行投资策略，返回结果"""
        trades: list[TradeRecord] = []

        # 初始资金状态
        cash = self.TOTAL_CAPITAL
        shares = 0.0
        buy_count = 0
        sell_count = 0
        reference_nav = None

        # 1. 在建仓日期买入初始金额
        initial_row = self.period_data.iloc[0]
        initial_nav = float(initial_row["unit_nav"])
        initial_shares = self.INITIAL_INVESTMENT / initial_nav
        shares += initial_shares
        cash -= self.INITIAL_INVESTMENT
        reference_nav = initial_nav

        trades.append(
            TradeRecord(
                date=initial_row["净值日期"].date(),
                trade_type=TradeType.INITIAL,
                nav=initial_nav,
                amount=self.INITIAL_INVESTMENT,
                shares=initial_shares,
                total_cost=self.INITIAL_INVESTMENT,
                remaining_cash=cash,
                note=f"初始建仓，参考净值: {initial_nav:.4f}",
            )
        )

        # 2. 遍历建仓日期到清仓日期之间的每个交易日（跳过第一天）
        for idx in range(1, len(self.period_data) - 1):
            row = self.period_data.iloc[idx]
            current_nav = float(row["unit_nav"])
            current_date = row["净值日期"].date()

            # 买入条件：当前净值 <= 参考净值 * (1 - 买入比例)
            if (
                buy_count < self.MAX_BUY_COUNT
                and current_nav <= reference_nav * (1 - self.buy_threshold)
                and cash >= self.BUY_AMOUNTS[buy_count]
            ):
                buy_amount = self.BUY_AMOUNTS[buy_count]
                buy_shares = buy_amount / current_nav
                shares += buy_shares
                cash -= buy_amount
                buy_count += 1
                reference_nav = current_nav

                trades.append(
                    TradeRecord(
                        date=current_date,
                        trade_type=TradeType.BUY,
                        nav=current_nav,
                        amount=buy_amount,
                        shares=buy_shares,
                        total_cost=sum(t.amount for t in trades),
                        remaining_cash=cash,
                        note=f"第{buy_count}次买入，触发下跌 {self.buy_threshold*100:.1f}%",
                    )
                )

            # 卖出条件：当前净值 >= 参考净值 * (1 + 卖出比例)
            elif (
                sell_count < self.MAX_SELL_COUNT
                and shares > 0
                and current_nav >= reference_nav * (1 + self.sell_threshold)
            ):
                # 计算卖出份额（基于阶梯金额）
                target_amount = self.SELL_AMOUNTS[sell_count]
                sell_shares = min(shares, target_amount / current_nav)
                sell_amount = sell_shares * current_nav
                shares -= sell_shares
                cash += sell_amount
                sell_count += 1
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
                        note=f"第{sell_count}次卖出，触发上涨 {self.sell_threshold*100:.1f}%",
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
        total_return_rate = (final_value - self.TOTAL_CAPITAL) / self.TOTAL_CAPITAL

        # 统计买卖次数（不含建仓和清仓）
        actual_buy_count = sum(1 for t in trades if t.trade_type == TradeType.BUY)
        actual_sell_count = sum(1 for t in trades if t.trade_type == TradeType.SELL)

        return StrategyResult(
            trades=trades,
            total_investment=self.TOTAL_CAPITAL,
            final_value=final_value,
            total_return_rate=total_return_rate,
            buy_count=actual_buy_count,
            sell_count=actual_sell_count,
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
        f"买入阈值: {result.buy_threshold*100:.1f}% (下跌触发)",
        f"卖出阈值: {result.sell_threshold*100:.1f}% (上涨触发)",
        "-" * 50,
        f"总投入金额: {result.total_investment:.2f} 元",
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
