from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from services.investment_strategy import InvestmentStrategy, StrategyResult

if TYPE_CHECKING:
    from datetime import date


@dataclass
class OptimizationResult:
    """优化结果"""

    optimal_buy_threshold: float
    optimal_sell_threshold: float
    max_return_rate: float
    optimal_result: StrategyResult
    all_results: list[tuple[float, float, float]]  # (buy_threshold, sell_threshold, return_rate)


class StrategyOptimizer:
    """策略优化器

    使用网格搜索寻找最优的买入和卖出比例阈值。
    """

    def __init__(
        self,
        nav_data: pd.DataFrame,
        start_date: date,
        end_date: date,
        buy_step: float = 0.005,
        sell_step: float = 0.005,
    ) -> None:
        """初始化优化器

        Args:
            nav_data: 基金净值数据
            start_date: 建仓日期
            end_date: 清仓日期
            buy_step: 买入比例搜索步长，默认 0.005 (0.5%)
            sell_step: 卖出比例搜索步长，默认 0.005 (0.5%)
        """
        self.nav_data = nav_data
        self.start_date = start_date
        self.end_date = end_date
        self.buy_step = buy_step
        self.sell_step = sell_step

    def optimize(self) -> OptimizationResult:
        """执行网格搜索优化

        搜索范围：
        - 下跌买入比例: 1% ~ 8%
        - 上涨卖出比例: 1% ~ 10%

        Returns:
            OptimizationResult: 包含最优参数和详细结果
        """
        # 定义搜索范围
        buy_range = [i * self.buy_step for i in range(2, 17)]  # 1% ~ 8%
        sell_range = [i * self.sell_step for i in range(2, 21)]  # 1% ~ 10%

        best_result = None
        best_return = float("-inf")
        optimal_buy = 0.0
        optimal_sell = 0.0
        all_results: list[tuple[float, float, float]] = []

        total_iterations = len(buy_range) * len(sell_range)
        current_iteration = 0

        for buy_threshold in buy_range:
            for sell_threshold in sell_range:
                current_iteration += 1

                try:
                    # 执行策略
                    strategy = InvestmentStrategy(
                        nav_data=self.nav_data,
                        start_date=self.start_date,
                        end_date=self.end_date,
                        buy_threshold=buy_threshold,
                        sell_threshold=sell_threshold,
                    )
                    result = strategy.execute()

                    # 记录结果
                    all_results.append(
                        (buy_threshold, sell_threshold, result.total_return_rate)
                    )

                    # 更新最优结果
                    if result.total_return_rate > best_return:
                        best_return = result.total_return_rate
                        optimal_buy = buy_threshold
                        optimal_sell = sell_threshold
                        best_result = result

                except Exception:
                    # 某些参数组合可能无法执行（如没有足够数据）
                    all_results.append((buy_threshold, sell_threshold, float("-inf")))
                    continue

        if best_result is None:
            raise ValueError("优化失败：没有找到可行的策略参数组合")

        return OptimizationResult(
            optimal_buy_threshold=optimal_buy,
            optimal_sell_threshold=optimal_sell,
            max_return_rate=best_return,
            optimal_result=best_result,
            all_results=all_results,
        )

    def optimize_quick(self) -> OptimizationResult:
        """快速优化（步长更大，速度更快）

        搜索范围：
        - 下跌买入比例: 1% ~ 8%，步长 1%
        - 上涨卖出比例: 1% ~ 10%，步长 1%
        """
        buy_range = [i * 0.01 for i in range(1, 9)]  # 1% ~ 8%
        sell_range = [i * 0.01 for i in range(1, 11)]  # 1% ~ 10%

        best_result = None
        best_return = float("-inf")
        optimal_buy = 0.0
        optimal_sell = 0.0
        all_results: list[tuple[float, float, float]] = []

        for buy_threshold in buy_range:
            for sell_threshold in sell_range:
                try:
                    strategy = InvestmentStrategy(
                        nav_data=self.nav_data,
                        start_date=self.start_date,
                        end_date=self.end_date,
                        buy_threshold=buy_threshold,
                        sell_threshold=sell_threshold,
                    )
                    result = strategy.execute()

                    all_results.append(
                        (buy_threshold, sell_threshold, result.total_return_rate)
                    )

                    if result.total_return_rate > best_return:
                        best_return = result.total_return_rate
                        optimal_buy = buy_threshold
                        optimal_sell = sell_threshold
                        best_result = result

                except Exception:
                    all_results.append((buy_threshold, sell_threshold, float("-inf")))
                    continue

        if best_result is None:
            raise ValueError("优化失败：没有找到可行的策略参数组合")

        return OptimizationResult(
            optimal_buy_threshold=optimal_buy,
            optimal_sell_threshold=optimal_sell,
            max_return_rate=best_return,
            optimal_result=best_result,
            all_results=all_results,
        )


def format_optimization_result(result: OptimizationResult) -> str:
    """格式化优化结果为可读字符串"""
    lines = [
        "=" * 50,
        "策略优化结果",
        "=" * 50,
        f"最优买入比例: {result.optimal_buy_threshold*100:.1f}% (下跌触发)",
        f"最优卖出比例: {result.optimal_sell_threshold*100:.1f}% (上涨触发)",
        f"最大收益率: {result.max_return_rate*100:+.2f}%",
        "-" * 50,
        "该参数下的详细交易记录:",
    ]

    # 添加详细交易结果
    strategy_text = format_strategy_result_compact(result.optimal_result)
    lines.append(strategy_text)

    lines.append("=" * 50)
    return "\n".join(lines)


def format_strategy_result_compact(result: StrategyResult) -> str:
    """格式化策略结果为紧凑格式"""
    lines = [
        f"  总投入: {result.total_investment:.2f} 元",
        f"  最终金额: {result.final_value:.2f} 元",
        f"  收益率: {result.total_return_rate*100:+.2f}%",
        f"  买入次数: {result.buy_count} 次",
        f"  卖出次数: {result.sell_count} 次",
        f"  交易明细 ({len(result.trades)} 笔):",
    ]

    for trade in result.trades:
        if trade.trade_type.value == "买入":
            lines.append(
                f"    买 {trade.date}: {trade.amount:.0f}元 @ {trade.nav:.4f}"
            )
        elif trade.trade_type.value == "卖出":
            lines.append(
                f"    卖 {trade.date}: {trade.amount:.0f}元 @ {trade.nav:.4f}"
            )
        elif trade.trade_type.value == "建仓":
            lines.append(
                f"    建 {trade.date}: {trade.amount:.0f}元 @ {trade.nav:.4f}"
            )
        elif trade.trade_type.value == "清仓":
            lines.append(
                f"    清 {trade.date}: {trade.amount:.0f}元 @ {trade.nav:.4f}"
            )

    return "\n".join(lines)
