from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PyQt6.QtWidgets import QVBoxLayout, QWidget

if TYPE_CHECKING:
    from services.models import BacktestResult, BacktestTrade


class ChartWidget(QWidget):
    """封装基金净值图表绘制逻辑，支持买卖点标记。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(10, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.ax = self.figure.add_subplot(111)
        self._setup_matplotlib_defaults()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        # 保存当前显示的数据，用于后续买卖点标记
        self._current_dataframe = None
        self._current_code = ""
        self._current_name = ""

        self.draw_placeholder()

    def _setup_matplotlib_defaults(self) -> None:
        # 配置中文与负号显示，避免标题及坐标轴乱码。
        self.figure.set_facecolor("#ffffff")
        self.ax.set_facecolor("#f8fafc")
        self.ax.grid(True, color="#e5e7eb", linestyle="--", linewidth=0.8, alpha=0.9)
        self.figure.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.14)
        self.figure.set_tight_layout(True)

    def draw_placeholder(self) -> None:
        self.ax.clear()
        self.ax.set_title("基金净值走势图", fontname="Microsoft YaHei")
        self.ax.text(
            0.5,
            0.5,
            "请输入基金代码并点击查询",
            ha="center",
            va="center",
            transform=self.ax.transAxes,
            fontsize=12,
            color="#6b7280",
            fontname="Microsoft YaHei",
        )
        self.ax.set_xlabel("日期", fontname="Microsoft YaHei")
        self.ax.set_ylabel("净值", fontname="Microsoft YaHei")
        self.ax.grid(True, color="#e5e7eb", linestyle="--", linewidth=0.8, alpha=0.9)
        self.canvas.draw_idle()

    def draw_history(self, code: str, name: str, dataframe) -> None:
        self._current_code = code
        self._current_name = name
        self._current_dataframe = dataframe.copy()

        self.ax.clear()

        date_series = dataframe["净值日期"]
        if "unit_nav" in dataframe.columns:
            self.ax.plot(
                date_series,
                dataframe["unit_nav"],
                color="#0ea5e9",
                linewidth=1.8,
                label="单位净值",
                zorder=2,
            )
        if "acc_nav" in dataframe.columns:
            self.ax.plot(
                date_series,
                dataframe["acc_nav"],
                color="#16a34a",
                linewidth=1.6,
                label="累计净值",
                alpha=0.85,
                zorder=2,
            )

        self.ax.set_title(f"{name} ({code}) 净值走势", fontname="Microsoft YaHei", fontsize=12)
        self.ax.set_xlabel("日期", fontname="Microsoft YaHei")
        self.ax.set_ylabel("净值", fontname="Microsoft YaHei")
        self.ax.grid(True, color="#e5e7eb", linestyle="--", linewidth=0.8, alpha=0.9, zorder=1)
        self.ax.xaxis.set_major_locator(MaxNLocator(nbins=8))
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        self.ax.tick_params(axis="x", rotation=25)
        self.ax.legend(loc="best", prop={"family": "Microsoft YaHei"})

        self.canvas.draw_idle()

    def draw_trades(self, strategy_result: StrategyResult) -> None:
        """在图表上标记买卖点

        Args:
            strategy_result: 策略执行结果，包含交易记录
        """
        if self._current_dataframe is None:
            return

        # 准备交易数据
        buy_dates = []
        buy_navs = []
        buy_amounts = []
        sell_dates = []
        sell_navs = []
        sell_amounts = []
        init_dates = []
        init_navs = []
        final_dates = []
        final_navs = []

        for trade in strategy_result.trades:
            from datetime import datetime

            trade_date = datetime.combine(trade.date, datetime.min.time())

            if trade.trade_type.value == "买入":
                buy_dates.append(trade_date)
                buy_navs.append(trade.nav)
                buy_amounts.append(trade.amount)
            elif trade.trade_type.value == "卖出":
                sell_dates.append(trade_date)
                sell_navs.append(trade.nav)
                sell_amounts.append(trade.amount)
            elif trade.trade_type.value == "建仓":
                init_dates.append(trade_date)
                init_navs.append(trade.nav)
            elif trade.trade_type.value == "清仓":
                final_dates.append(trade_date)
                final_navs.append(trade.nav)

        # 绘制买入点（绿色上三角）
        if buy_dates:
            self.ax.scatter(
                buy_dates,
                buy_navs,
                marker="^",
                color="#22c55e",
                s=100,
                zorder=5,
                label=f"买入 ({len(buy_dates)}次)",
                edgecolors="white",
                linewidths=1,
            )

        # 绘制卖出点（红色下三角）
        if sell_dates:
            self.ax.scatter(
                sell_dates,
                sell_navs,
                marker="v",
                color="#ef4444",
                s=100,
                zorder=5,
                label=f"卖出 ({len(sell_dates)}次)",
                edgecolors="white",
                linewidths=1,
            )

        # 绘制建仓点（蓝色圆形）
        if init_dates:
            self.ax.scatter(
                init_dates,
                init_navs,
                marker="o",
                color="#3b82f6",
                s=120,
                zorder=5,
                label="建仓",
                edgecolors="white",
                linewidths=1,
            )

        # 绘制清仓点（紫色菱形）
        if final_dates:
            self.ax.scatter(
                final_dates,
                final_navs,
                marker="D",
                color="#a855f7",
                s=100,
                zorder=5,
                label="清仓",
                edgecolors="white",
                linewidths=1,
            )

        # 更新图例和标题
        self.ax.legend(loc="best", prop={"family": "Microsoft YaHei"})
        self.ax.set_title(
            f"{self._current_name} ({self._current_code}) 净值走势 - 收益率: {strategy_result.total_return_rate*100:+.2f}%",
            fontname="Microsoft YaHei",
            fontsize=12,
        )

        self.canvas.draw_idle()

    def clear_trades(self) -> None:
        """清除买卖点标记，重新绘制基础图表"""
        if self._current_dataframe is not None:
            self.draw_history(
                self._current_code, self._current_name, self._current_dataframe
            )

    def draw_three_lines(
        self,
        opportunity: float | None = None,
        middle: float | None = None,
        danger: float | None = None,
    ) -> None:
        """在图表上绘制三条估值线（水平虚线）。

        Args:
            opportunity: 机会线净值
            middle: 中位线净值
            danger: 危险线净值
        """
        if opportunity is not None:
            self.ax.axhline(
                y=opportunity, color="#22c55e", linestyle="--", linewidth=1.2,
                alpha=0.8, label=f"机会线 {opportunity:.4f}", zorder=3,
            )
        if middle is not None:
            self.ax.axhline(
                y=middle, color="#f59e0b", linestyle="--", linewidth=1.2,
                alpha=0.8, label=f"中位线 {middle:.4f}", zorder=3,
            )
        if danger is not None:
            self.ax.axhline(
                y=danger, color="#ef4444", linestyle="--", linewidth=1.2,
                alpha=0.8, label=f"危险线 {danger:.4f}", zorder=3,
            )

        self.ax.legend(loc="best", prop={"family": "Microsoft YaHei"})
        self.canvas.draw_idle()

    def draw_backtest_trades(self, result: BacktestResult) -> None:
        """在图表上标记回测买卖点。

        Args:
            result: 回测结果
        """
        from datetime import datetime
        from services.models import TradeType

        if self._current_dataframe is None:
            return

        buy_dates, buy_navs = [], []
        sell_dates, sell_navs = [], []
        init_dates, init_navs = [], []
        final_dates, final_navs = [], []

        for trade in result.trades:
            if trade.trade_date is None:
                continue
            trade_dt = datetime.combine(trade.trade_date, datetime.min.time())

            if trade.trade_type in (TradeType.BUY,):
                buy_dates.append(trade_dt)
                buy_navs.append(trade.nav)
            elif trade.trade_type in (TradeType.SELL, TradeType.TAKE_PROFIT):
                sell_dates.append(trade_dt)
                sell_navs.append(trade.nav)
            elif trade.trade_type == TradeType.INITIAL:
                init_dates.append(trade_dt)
                init_navs.append(trade.nav)
            elif trade.trade_type == TradeType.FINAL:
                final_dates.append(trade_dt)
                final_navs.append(trade.nav)

        if buy_dates:
            self.ax.scatter(
                buy_dates, buy_navs, marker="^", color="#22c55e",
                s=100, zorder=5, label=f"买入 ({len(buy_dates)}次)",
                edgecolors="white", linewidths=1,
            )
        if sell_dates:
            self.ax.scatter(
                sell_dates, sell_navs, marker="v", color="#ef4444",
                s=100, zorder=5, label=f"卖出 ({len(sell_dates)}次)",
                edgecolors="white", linewidths=1,
            )
        if init_dates:
            self.ax.scatter(
                init_dates, init_navs, marker="o", color="#3b82f6",
                s=120, zorder=5, label="建仓",
                edgecolors="white", linewidths=1,
            )
        if final_dates:
            self.ax.scatter(
                final_dates, final_navs, marker="D", color="#a855f7",
                s=100, zorder=5, label="清仓",
                edgecolors="white", linewidths=1,
            )

        self.ax.legend(loc="best", prop={"family": "Microsoft YaHei"})
        title = f"{self._current_name} ({self._current_code}) 回测结果 - 收益率: {result.total_return_rate*100:+.2f}%"
        self.ax.set_title(title, fontname="Microsoft YaHei", fontsize=12)
        self.canvas.draw_idle()
