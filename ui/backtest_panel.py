"""模式B：策略回测面板 — 参数设定 + 图表 + 回测结果"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDateEdit,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from services.fund_service import FundDataError, FundService
from services.models import BacktestResult, Fund, StrategyType, TradeType
from services.strategy_engine import StrategyEngine
from ui.chart_widget import ChartWidget

if TYPE_CHECKING:
    import pandas as pd


class BacktestWorker(QObject):
    """回测工作线程"""

    finished = pyqtSignal(object)  # BacktestResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        nav_data: pd.DataFrame,
        fund: Fund,
        start_date: date,
        end_date: date,
        threshold: float = 0.05,
    ) -> None:
        super().__init__()
        self.nav_data = nav_data
        self.fund = fund
        self.start_date = start_date
        self.end_date = end_date
        self.threshold = threshold

    def run(self) -> None:
        try:
            engine = StrategyEngine(threshold=self.threshold)
            result = engine.backtest(self.nav_data, self.fund, self.start_date, self.end_date)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"回测失败：{exc}")


class BacktestPanel(QWidget):
    """策略回测面板（模式B右侧）"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fund_service = FundService()
        self._current_fund: Fund | None = None
        self._nav_data: pd.DataFrame | None = None
        self._thread: QThread | None = None
        self._worker: BacktestWorker | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ===== ① 回测参数区 =====
        param_group = QGroupBox("回测参数")
        param_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(8)

        # 三线设定
        lines_row = QHBoxLayout()
        lines_row.addWidget(QLabel("机会线:"))
        self.opportunity_spin = QDoubleSpinBox()
        self.opportunity_spin.setRange(0.01, 99.99)
        self.opportunity_spin.setDecimals(4)
        self.opportunity_spin.setSingleStep(0.01)
        self.opportunity_spin.setFont(QFont("Microsoft YaHei", 9))
        lines_row.addWidget(self.opportunity_spin)

        lines_row.addWidget(QLabel("中位线:"))
        self.middle_spin = QDoubleSpinBox()
        self.middle_spin.setRange(0.01, 99.99)
        self.middle_spin.setDecimals(4)
        self.middle_spin.setSingleStep(0.01)
        self.middle_spin.setFont(QFont("Microsoft YaHei", 9))
        lines_row.addWidget(self.middle_spin)

        lines_row.addWidget(QLabel("危险线:"))
        self.danger_spin = QDoubleSpinBox()
        self.danger_spin.setRange(0.01, 99.99)
        self.danger_spin.setDecimals(4)
        self.danger_spin.setSingleStep(0.01)
        self.danger_spin.setFont(QFont("Microsoft YaHei", 9))
        lines_row.addWidget(self.danger_spin)
        param_layout.addLayout(lines_row)

        # 日期范围
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("起始:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(date.today().replace(year=date.today().year - 1))
        self.start_date_edit.setFont(QFont("Microsoft YaHei", 9))
        date_row.addWidget(self.start_date_edit)

        date_row.addWidget(QLabel("结束:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.setFont(QFont("Microsoft YaHei", 9))
        date_row.addWidget(self.end_date_edit)
        param_layout.addLayout(date_row)

        # 额外参数
        extra_row = QHBoxLayout()
        extra_row.addWidget(QLabel("每份金额:"))
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(100, 100000)
        self.amount_spin.setValue(1250)
        self.amount_spin.setSingleStep(100)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSuffix(" 元")
        self.amount_spin.setFont(QFont("Microsoft YaHei", 9))
        extra_row.addWidget(self.amount_spin)

        extra_row.addWidget(QLabel("总份数:"))
        self.shares_spin = QSpinBox()
        self.shares_spin.setRange(5, 20)
        self.shares_spin.setValue(10)
        self.shares_spin.setFont(QFont("Microsoft YaHei", 9))
        extra_row.addWidget(self.shares_spin)

        extra_row.addWidget(QLabel("阈值:"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(1.0, 10.0)
        self.threshold_spin.setValue(5.0)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setSuffix("%")
        self.threshold_spin.setFont(QFont("Microsoft YaHei", 9))
        extra_row.addWidget(self.threshold_spin)

        extra_row.addWidget(QLabel("主仓%:"))
        self.main_ratio_spin = QSpinBox()
        self.main_ratio_spin.setRange(10, 90)
        self.main_ratio_spin.setValue(60)
        self.main_ratio_spin.setSuffix("%")
        self.main_ratio_spin.setFont(QFont("Microsoft YaHei", 9))
        extra_row.addWidget(self.main_ratio_spin)
        param_layout.addLayout(extra_row)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("开始回测")
        self.run_btn.setFixedHeight(36)
        self.run_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run_backtest)
        btn_row.addWidget(self.run_btn)
        param_layout.addLayout(btn_row)

        layout.addWidget(param_group)

        # ===== ② 图表区 + ③ 结果区（上下分割） =====
        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)

        # 图表
        self.chart = ChartWidget()
        splitter.addWidget(self.chart)

        # 结果文本
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Microsoft YaHei", 9))
        self.result_text.setPlaceholderText("回测结果将在此显示...")
        self.result_text.setMaximumHeight(200)
        splitter.addWidget(self.result_text)

        splitter.setSizes([500, 200])
        layout.addWidget(splitter, stretch=1)

    def set_fund(self, fund: Fund) -> None:
        """设置当前基金，加载净值数据"""
        self._current_fund = fund

        # 设置三线默认值
        if fund.opportunity_line:
            self.opportunity_spin.setValue(fund.opportunity_line)
        if fund.middle_line:
            self.middle_spin.setValue(fund.middle_line)
        if fund.danger_line:
            self.danger_spin.setValue(fund.danger_line)

        # 设置主仓比例
        self.main_ratio_spin.setValue(int(fund.main_ratio * 100))
        self.amount_spin.setValue(fund.per_share_amount)
        self.shares_spin.setValue(fund.total_shares_count)

        # 加载净值数据
        self._load_nav_data(fund.code)

    def _load_nav_data(self, code: str) -> None:
        """加载基金净值数据"""
        try:
            history = self.fund_service.get_fund_history(code)
            self._nav_data = history.dataframe

            # 绘制图表
            self.chart.draw_history(history.code, history.name, self._nav_data)

            # 更新日期范围
            if not self._nav_data.empty:
                import pandas as pd
                min_date = self._nav_data["净值日期"].min()
                max_date = self._nav_data["净值日期"].max()
                self.start_date_edit.setDateRange(min_date.date(), max_date.date())
                self.end_date_edit.setDateRange(min_date.date(), max_date.date())
                default_start = max(min_date, max_date - pd.Timedelta(days=365))
                self.start_date_edit.setDate(default_start.date())
                self.end_date_edit.setDate(max_date.date())

            self.run_btn.setEnabled(True)
        except FundDataError as exc:
            QMessageBox.warning(self, "数据加载失败", str(exc))
            self.run_btn.setEnabled(False)

    def _run_backtest(self) -> None:
        """执行回测"""
        if self._nav_data is None or self._current_fund is None:
            return

        if self._thread and self._thread.isRunning():
            return

        # 构造回测用的 Fund 配置
        fund = Fund(
            code=self._current_fund.code,
            name=self._current_fund.name,
            opportunity_line=self.opportunity_spin.value(),
            middle_line=self.middle_spin.value(),
            danger_line=self.danger_spin.value(),
            per_share_amount=self.amount_spin.value(),
            total_shares_count=self.shares_spin.value(),
            main_ratio=self.main_ratio_spin.value() / 100.0,
            swing_ratio=1.0 - self.main_ratio_spin.value() / 100.0,
        )

        # 验证三线
        if not (fund.opportunity_line < fund.middle_line < fund.danger_line):
            QMessageBox.warning(self, "参数错误", "三线必须满足：机会线 < 中位线 < 危险线")
            return

        start = self.start_date_edit.date().toPyDate()
        end = self.end_date_edit.date().toPyDate()
        if start >= end:
            QMessageBox.warning(self, "参数错误", "起始日期必须早于结束日期")
            return

        threshold = self.threshold_spin.value() / 100.0

        self.run_btn.setEnabled(False)
        self.run_btn.setText("回测中...")

        # 清除旧标记
        self.chart.clear_trades()

        self._thread = QThread(self)
        self._worker = BacktestWorker(self._nav_data, fund, start, end, threshold)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_backtest_done)
        self._worker.failed.connect(self._on_backtest_failed)
        self._worker.finished.connect(self._cleanup_thread)
        self._worker.failed.connect(self._cleanup_thread)
        self._thread.start()

    def _on_backtest_done(self, result: BacktestResult) -> None:
        """回测完成"""
        # 绘制三线
        self.chart.draw_three_lines(
            self.opportunity_spin.value(),
            self.middle_spin.value(),
            self.danger_spin.value(),
        )
        # 绘制买卖点
        self.chart.draw_backtest_trades(result)

        # 显示结果文本
        self.result_text.setPlainText(self._format_result(result))

    def _on_backtest_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "回测失败", msg)
        self.result_text.setPlainText(f"回测失败: {msg}")

    def _cleanup_thread(self) -> None:
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始回测")
        if self._thread:
            self._thread.quit()
            self._thread.wait(1000)
            self._thread.deleteLater()
            self._thread = None
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    @staticmethod
    def _format_result(r: BacktestResult) -> str:
        lines = [
            "=" * 45,
            "三策略回测结果",
            "=" * 45,
            f"回测区间: {r.start_date} ~ {r.end_date}",
            f"总资金: {r.total_investment:.0f} 元",
            f"最终资产: {r.final_value:.0f} 元",
            f"总收益率: {r.total_return_rate*100:+.2f}%",
            f"最大回撤: {r.max_drawdown*100:.2f}%",
            "-" * 45,
            f"买入次数: {r.buy_count}  卖出次数: {r.sell_count}",
            f"策略分布: 建仓{r.build_count}次 | 波动{r.swing_count}次 | 止盈{r.take_profit_count}次",
            "-" * 45,
            "交易明细:",
        ]
        for t in r.trades:
            d = t.trade_date.isoformat() if t.trade_date else "?"
            lines.append(f"  [{d}] {t.trade_type.value} {t.amount:.0f}元 @ {t.nav:.4f} ({t.trigger_reason})")
        lines.append("=" * 45)
        return "\n".join(lines)

    def clear(self) -> None:
        """清空面板"""
        self.chart.draw_placeholder()
        self.result_text.clear()
        self.run_btn.setEnabled(False)
        self._nav_data = None
        self._current_fund = None
