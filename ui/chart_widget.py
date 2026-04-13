from __future__ import annotations

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class ChartWidget(QWidget):
    """封装基金净值图表绘制逻辑。"""

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
        self.ax.clear()

        date_series = dataframe["净值日期"]
        if "unit_nav" in dataframe.columns:
            self.ax.plot(
                date_series,
                dataframe["unit_nav"],
                color="#0ea5e9",
                linewidth=1.8,
                label="单位净值",
            )
        if "acc_nav" in dataframe.columns:
            self.ax.plot(
                date_series,
                dataframe["acc_nav"],
                color="#16a34a",
                linewidth=1.6,
                label="累计净值",
                alpha=0.85,
            )

        self.ax.set_title(f"{name} ({code}) 净值走势", fontname="Microsoft YaHei", fontsize=12)
        self.ax.set_xlabel("日期", fontname="Microsoft YaHei")
        self.ax.set_ylabel("净值", fontname="Microsoft YaHei")
        self.ax.grid(True, color="#e5e7eb", linestyle="--", linewidth=0.8, alpha=0.9)
        self.ax.xaxis.set_major_locator(MaxNLocator(nbins=8))
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        self.ax.tick_params(axis="x", rotation=25)
        self.ax.legend(loc="best", prop={"family": "Microsoft YaHei"})

        self.canvas.draw_idle()
