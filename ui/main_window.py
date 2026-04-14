from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDateEdit,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from services.fund_service import FundDataError, FundHistory, FundService
from services.investment_strategy import InvestmentStrategy, format_strategy_result
from services.optimizer import StrategyOptimizer, format_optimization_result
from ui.chart_widget import ChartWidget

if TYPE_CHECKING:
    from services.investment_strategy import StrategyResult
    from services.optimizer import OptimizationResult


class FundQueryWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service: FundService, code: str) -> None:
        super().__init__()
        self.service = service
        self.code = code

    def run(self) -> None:
        try:
            history = self.service.get_fund_history(self.code)
            self.finished.emit(history)
        except FundDataError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"未知错误：{exc}")


class StrategyWorker(QObject):
    """策略计算工作线程"""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        nav_data,
        start_date: date,
        end_date: date,
        buy_threshold: float,
        sell_threshold: float,
        total_capital: float = 10000.0,
        max_consecutive_buy: int = 5,
        max_consecutive_sell: int = 5,
    ) -> None:
        super().__init__()
        self.nav_data = nav_data
        self.start_date = start_date
        self.end_date = end_date
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.total_capital = total_capital
        self.max_consecutive_buy = max_consecutive_buy
        self.max_consecutive_sell = max_consecutive_sell

    def run(self) -> None:
        try:
            strategy = InvestmentStrategy(
                nav_data=self.nav_data,
                start_date=self.start_date,
                end_date=self.end_date,
                buy_threshold=self.buy_threshold,
                sell_threshold=self.sell_threshold,
                total_capital=self.total_capital,
                max_consecutive_buy=self.max_consecutive_buy,
                max_consecutive_sell=self.max_consecutive_sell,
            )
            result = strategy.execute()
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"策略计算失败：{exc}")


class OptimizerWorker(QObject):
    """优化器工作线程"""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(
        self,
        nav_data,
        start_date: date,
        end_date: date,
        quick_mode: bool = True,
        total_capital: float = 10000.0,
        max_consecutive_buy: int = 5,
        max_consecutive_sell: int = 5,
    ) -> None:
        super().__init__()
        self.nav_data = nav_data
        self.start_date = start_date
        self.end_date = end_date
        self.quick_mode = quick_mode
        self.total_capital = total_capital
        self.max_consecutive_buy = max_consecutive_buy
        self.max_consecutive_sell = max_consecutive_sell

    def run(self) -> None:
        try:
            optimizer = StrategyOptimizer(
                nav_data=self.nav_data,
                start_date=self.start_date,
                end_date=self.end_date,
                total_capital=self.total_capital,
                max_consecutive_buy=self.max_consecutive_buy,
                max_consecutive_sell=self.max_consecutive_sell,
            )

            if self.quick_mode:
                result = optimizer.optimize_quick()
            else:
                result = optimizer.optimize()

            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(f"优化失败：{exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("基金投资分析上位机")
        self.resize(1400, 800)
        self.setMinimumSize(1100, 700)

        # 服务实例
        self.fund_service = FundService()

        # 当前数据
        self.current_history: FundHistory | None = None
        self.current_strategy_result: StrategyResult | None = None

        # 线程
        self.query_thread: QThread | None = None
        self.query_worker: FundQueryWorker | None = None
        self.strategy_thread: QThread | None = None
        self.strategy_worker: StrategyWorker | None = None
        self.optimizer_thread: QThread | None = None
        self.optimizer_worker: OptimizerWorker | None = None

        # 构建UI
        self._build_ui()

    def _build_ui(self) -> None:
        """构建主界面"""
        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局：左右分栏
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 创建分割器
        splitter = QSplitter()
        main_layout.addWidget(splitter)

        # 左侧：图表区域（70%宽度）
        left_panel = self._build_left_panel()
        splitter.addWidget(left_panel)

        # 右侧：参数和控制区域（30%宽度）
        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)

        # 设置分割比例
        splitter.setSizes([1000, 400])

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪 - 请输入基金代码查询")

    def _build_left_panel(self) -> QWidget:
        """构建左侧面板（图表区域）"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 基金代码查询栏
        query_bar = QHBoxLayout()
        query_bar.setSpacing(8)

        code_label = QLabel("基金代码:")
        code_label.setFont(QFont("Microsoft YaHei", 10))
        query_bar.addWidget(code_label)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("请输入 6 位基金代码，例如 161725")
        self.code_input.setMaxLength(6)
        self.code_input.setFixedHeight(34)
        self.code_input.setFont(QFont("Microsoft YaHei", 10))
        self.code_input.setText("161725")
        self.code_input.returnPressed.connect(self.query_fund)
        query_bar.addWidget(self.code_input, stretch=1)

        self.query_button = QPushButton("查询净值")
        self.query_button.setFixedHeight(34)
        self.query_button.setFont(QFont("Microsoft YaHei", 10))
        self.query_button.clicked.connect(self.query_fund)
        query_bar.addWidget(self.query_button)

        layout.addLayout(query_bar)

        # 图表控件
        self.chart = ChartWidget()
        layout.addWidget(self.chart, stretch=1)

        return panel

    def _build_right_panel(self) -> QWidget:
        """构建右侧面板（参数和结果区域）"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ===== 参数输入组 =====
        param_group = QGroupBox("投资参数设置")
        param_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(10)

        # 总资金
        total_capital_layout = QHBoxLayout()
        total_capital_label = QLabel("总资金:")
        total_capital_label.setFont(QFont("Microsoft YaHei", 9))
        total_capital_layout.addWidget(total_capital_label)

        self.total_capital_spin = QDoubleSpinBox()
        self.total_capital_spin.setRange(1000.0, 1000000.0)
        self.total_capital_spin.setValue(10000.0)  # 默认值1万
        self.total_capital_spin.setSingleStep(1000.0)
        self.total_capital_spin.setDecimals(0)
        self.total_capital_spin.setSuffix(" 元")
        self.total_capital_spin.setFont(QFont("Microsoft YaHei", 9))
        total_capital_layout.addWidget(self.total_capital_spin)
        param_layout.addLayout(total_capital_layout)

        # 建仓日期
        start_date_layout = QHBoxLayout()
        start_date_label = QLabel("建仓日期:")
        start_date_label.setFont(QFont("Microsoft YaHei", 9))
        start_date_layout.addWidget(start_date_label)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(date.today().replace(year=date.today().year - 1))
        self.start_date_edit.setFont(QFont("Microsoft YaHei", 9))
        start_date_layout.addWidget(self.start_date_edit)
        param_layout.addLayout(start_date_layout)

        # 清仓日期
        end_date_layout = QHBoxLayout()
        end_date_label = QLabel("清仓日期:")
        end_date_label.setFont(QFont("Microsoft YaHei", 9))
        end_date_layout.addWidget(end_date_label)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.setFont(QFont("Microsoft YaHei", 9))
        end_date_layout.addWidget(self.end_date_edit)
        param_layout.addLayout(end_date_layout)

        # 下跌买入比例
        buy_threshold_layout = QHBoxLayout()
        buy_threshold_label = QLabel("下跌买入比例:")
        buy_threshold_label.setFont(QFont("Microsoft YaHei", 9))
        buy_threshold_layout.addWidget(buy_threshold_label)

        self.buy_threshold_spin = QDoubleSpinBox()
        self.buy_threshold_spin.setRange(1.0, 8.0)
        self.buy_threshold_spin.setValue(4.0)  # 默认4%
        self.buy_threshold_spin.setSingleStep(0.5)
        self.buy_threshold_spin.setDecimals(1)
        self.buy_threshold_spin.setSuffix("%")
        self.buy_threshold_spin.setFont(QFont("Microsoft YaHei", 9))
        buy_threshold_layout.addWidget(self.buy_threshold_spin)
        param_layout.addLayout(buy_threshold_layout)

        # 上涨卖出比例
        sell_threshold_layout = QHBoxLayout()
        sell_threshold_label = QLabel("上涨卖出比例:")
        sell_threshold_label.setFont(QFont("Microsoft YaHei", 9))
        sell_threshold_layout.addWidget(sell_threshold_label)

        self.sell_threshold_spin = QDoubleSpinBox()
        self.sell_threshold_spin.setRange(1.0, 10.0)
        self.sell_threshold_spin.setValue(2.0)  # 默认2%
        self.sell_threshold_spin.setSingleStep(0.5)
        self.sell_threshold_spin.setDecimals(1)
        self.sell_threshold_spin.setSuffix("%")
        self.sell_threshold_spin.setFont(QFont("Microsoft YaHei", 9))
        sell_threshold_layout.addWidget(self.sell_threshold_spin)
        param_layout.addLayout(sell_threshold_layout)

        # 最多连续买入次数
        max_buy_layout = QHBoxLayout()
        max_buy_label = QLabel("最多连续买入:")
        max_buy_label.setFont(QFont("Microsoft YaHei", 9))
        max_buy_layout.addWidget(max_buy_label)

        self.max_buy_spin = QDoubleSpinBox()
        self.max_buy_spin.setRange(1.0, 10.0)
        self.max_buy_spin.setValue(5.0)  # 默认5次
        self.max_buy_spin.setSingleStep(1.0)
        self.max_buy_spin.setDecimals(0)
        self.max_buy_spin.setSuffix(" 次")
        self.max_buy_spin.setFont(QFont("Microsoft YaHei", 9))
        max_buy_layout.addWidget(self.max_buy_spin)
        param_layout.addLayout(max_buy_layout)

        # 最多连续卖出次数
        max_sell_layout = QHBoxLayout()
        max_sell_label = QLabel("最多连续卖出:")
        max_sell_label.setFont(QFont("Microsoft YaHei", 9))
        max_sell_layout.addWidget(max_sell_label)

        self.max_sell_spin = QDoubleSpinBox()
        self.max_sell_spin.setRange(1.0, 10.0)
        self.max_sell_spin.setValue(5.0)  # 默认5次
        self.max_sell_spin.setSingleStep(1.0)
        self.max_sell_spin.setDecimals(0)
        self.max_sell_spin.setSuffix(" 次")
        self.max_sell_spin.setFont(QFont("Microsoft YaHei", 9))
        max_sell_layout.addWidget(self.max_sell_spin)
        param_layout.addLayout(max_sell_layout)

        # 操作按钮
        button_layout = QHBoxLayout()

        self.calc_button = QPushButton("计算收益率")
        self.calc_button.setFixedHeight(36)
        self.calc_button.setFont(QFont("Microsoft YaHei", 10))
        self.calc_button.setEnabled(False)
        self.calc_button.clicked.connect(self.calculate_strategy)
        button_layout.addWidget(self.calc_button)

        self.optimize_button = QPushButton("自动优化参数")
        self.optimize_button.setFixedHeight(36)
        self.optimize_button.setFont(QFont("Microsoft YaHei", 10))
        self.optimize_button.setEnabled(False)
        self.optimize_button.clicked.connect(self.optimize_parameters)
        button_layout.addWidget(self.optimize_button)

        param_layout.addLayout(button_layout)

        # 优化进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        param_layout.addWidget(self.progress_bar)

        layout.addWidget(param_group)

        # ===== 结果显示组 =====
        result_group = QGroupBox("投资分析结果")
        result_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        result_layout = QVBoxLayout(result_group)

        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Microsoft YaHei", 9))
        self.result_text.setPlaceholderText("请先查询基金净值，然后设置参数并点击计算...")
        result_layout.addWidget(self.result_text)

        layout.addWidget(result_group, stretch=1)

        # 投资规则说明
        info_label = QLabel(
            "投资规则:\n"
            "• 总资金可配置（默认10000元）\n"
            "• 初始建仓为总资金的25%\n"
            "• 连续买入限制: 最多连续买入N次后必须等待上涨卖出\n"
            "• 连续卖出限制: 最多连续卖出N次后必须等待下跌买入"
        )
        info_label.setFont(QFont("Microsoft YaHei", 8))
        info_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(info_label)

        return panel

    # ==================== 查询功能 ====================

    def query_fund(self) -> None:
        """查询基金净值数据"""
        if self.query_thread is not None and self.query_thread.isRunning():
            return

        code = self.code_input.text().strip()
        if not code or len(code) != 6 or not code.isdigit():
            QMessageBox.warning(self, "输入错误", "请输入正确的6位数字基金代码")
            return

        self.query_button.setEnabled(False)
        self.calc_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.status.showMessage(f"正在查询基金 {code}...")

        self.query_thread = QThread(self)
        self.query_worker = FundQueryWorker(self.fund_service, code)
        self.query_worker.moveToThread(self.query_thread)

        self.query_thread.started.connect(self.query_worker.run)
        self.query_worker.finished.connect(self._on_query_success)
        self.query_worker.failed.connect(self._on_query_failed)
        self.query_worker.finished.connect(self._cleanup_query_thread)
        self.query_worker.failed.connect(self._cleanup_query_thread)
        self.query_thread.start()

    def _on_query_success(self, history: FundHistory) -> None:
        """查询成功回调"""
        self.current_history = history

        # 绘制图表
        self.chart.draw_history(history.code, history.name, history.dataframe)

        # 更新日期选择器的范围
        if not history.dataframe.empty:
            min_date = history.dataframe["净值日期"].min()
            max_date = history.dataframe["净值日期"].max()
            self.start_date_edit.setDateRange(min_date.date(), max_date.date())
            self.end_date_edit.setDateRange(min_date.date(), max_date.date())

            # 默认选择最近一年的数据
            default_start = max(min_date, max_date - pd.Timedelta(days=365))
            self.start_date_edit.setDate(default_start.date())
            self.end_date_edit.setDate(max_date.date())

        # 启用计算按钮
        self.calc_button.setEnabled(True)
        self.optimize_button.setEnabled(True)

        self.status.showMessage(
            f"查询成功：{history.name} ({history.code})，共 {len(history.dataframe)} 条记录"
        )

        # 显示基本信息
        self.result_text.setPlainText(
            f"基金名称: {history.name}\n"
            f"基金代码: {history.code}\n"
            f"数据条数: {len(history.dataframe)}\n"
            f"数据范围: {history.dataframe['净值日期'].min().date()} ~ "
            f"{history.dataframe['净值日期'].max().date()}\n\n"
            f"请设置投资参数后点击计算或优化按钮。"
        )

    def _on_query_failed(self, message: str) -> None:
        """查询失败回调"""
        self.status.showMessage("查询失败")
        QMessageBox.warning(self, "查询失败", message)
        self.result_text.setPlainText(f"查询失败: {message}")

    def _cleanup_query_thread(self) -> None:
        """清理查询线程"""
        self.query_button.setEnabled(True)
        if self.query_thread is not None:
            self.query_thread.quit()
            self.query_thread.wait(1000)
            self.query_thread.deleteLater()
            self.query_thread = None
        if self.query_worker is not None:
            self.query_worker.deleteLater()
            self.query_worker = None

    # ==================== 策略计算功能 ====================

    def calculate_strategy(self) -> None:
        """计算投资策略收益率"""
        if self.current_history is None:
            QMessageBox.warning(self, "提示", "请先查询基金净值数据")
            return

        if self.strategy_thread is not None and self.strategy_thread.isRunning():
            return

        # 获取参数
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        buy_threshold = self.buy_threshold_spin.value() / 100.0
        sell_threshold = self.sell_threshold_spin.value() / 100.0
        total_capital = self.total_capital_spin.value()
        max_consecutive_buy = int(self.max_buy_spin.value())
        max_consecutive_sell = int(self.max_sell_spin.value())

        # 验证日期
        if start_date >= end_date:
            QMessageBox.warning(self, "参数错误", "建仓日期必须早于清仓日期")
            return

        # 重置图表，清除之前的买卖点标记
        self.chart.clear_trades()

        self.calc_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.status.showMessage("正在计算投资策略...")

        self.strategy_thread = QThread(self)
        self.strategy_worker = StrategyWorker(
            nav_data=self.current_history.dataframe,
            start_date=start_date,
            end_date=end_date,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            total_capital=total_capital,
            max_consecutive_buy=max_consecutive_buy,
            max_consecutive_sell=max_consecutive_sell,
        )
        self.strategy_worker.moveToThread(self.strategy_thread)

        self.strategy_thread.started.connect(self.strategy_worker.run)
        self.strategy_worker.finished.connect(self._on_strategy_success)
        self.strategy_worker.failed.connect(self._on_strategy_failed)
        self.strategy_worker.finished.connect(self._cleanup_strategy_thread)
        self.strategy_worker.failed.connect(self._cleanup_strategy_thread)
        self.strategy_thread.start()

    def _on_strategy_success(self, result: StrategyResult) -> None:
        """策略计算成功回调"""
        self.current_strategy_result = result

        # 在图表上标记买卖点
        self.chart.draw_trades(result)

        # 显示结果
        result_text = format_strategy_result(result)
        self.result_text.setPlainText(result_text)

        self.status.showMessage(
            f"计算完成：收益率 {result.total_return_rate*100:+.2f}%，"
            f"买入{result.buy_count}次，卖出{result.sell_count}次"
        )

    def _on_strategy_failed(self, message: str) -> None:
        """策略计算失败回调"""
        self.status.showMessage("计算失败")
        QMessageBox.warning(self, "计算失败", message)
        self.result_text.setPlainText(f"计算失败: {message}")

    def _cleanup_strategy_thread(self) -> None:
        """清理策略线程"""
        self.calc_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        if self.strategy_thread is not None:
            self.strategy_thread.quit()
            self.strategy_thread.wait(1000)
            self.strategy_thread.deleteLater()
            self.strategy_thread = None
        if self.strategy_worker is not None:
            self.strategy_worker.deleteLater()
            self.strategy_worker = None

    # ==================== 优化功能 ====================

    def optimize_parameters(self) -> None:
        """自动优化买卖参数"""
        if self.current_history is None:
            QMessageBox.warning(self, "提示", "请先查询基金净值数据")
            return

        if self.optimizer_thread is not None and self.optimizer_thread.isRunning():
            return

        # 获取参数
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        total_capital = self.total_capital_spin.value()
        max_consecutive_buy = int(self.max_buy_spin.value())
        max_consecutive_sell = int(self.max_sell_spin.value())

        # 验证日期
        if start_date >= end_date:
            QMessageBox.warning(self, "参数错误", "建仓日期必须早于清仓日期")
            return

        # 重置图表，清除之前的买卖点标记
        self.chart.clear_trades()

        self.calc_button.setEnabled(False)
        self.optimize_button.setEnabled(False)
        self.status.showMessage("正在优化参数，请稍候...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度

        self.optimizer_thread = QThread(self)
        # 使用快速优化模式
        self.optimizer_worker = OptimizerWorker(
            nav_data=self.current_history.dataframe,
            start_date=start_date,
            end_date=end_date,
            quick_mode=True,
            total_capital=total_capital,
            max_consecutive_buy=max_consecutive_buy,
            max_consecutive_sell=max_consecutive_sell,
        )
        self.optimizer_worker.moveToThread(self.optimizer_thread)

        self.optimizer_thread.started.connect(self.optimizer_worker.run)
        self.optimizer_worker.finished.connect(self._on_optimize_success)
        self.optimizer_worker.failed.connect(self._on_optimize_failed)
        self.optimizer_worker.finished.connect(self._cleanup_optimizer_thread)
        self.optimizer_worker.failed.connect(self._cleanup_optimizer_thread)
        self.optimizer_thread.start()

    def _on_optimize_success(self, result: OptimizationResult) -> None:
        """优化成功回调"""
        # 更新参数输入框
        self.buy_threshold_spin.setValue(result.optimal_buy_threshold * 100)
        self.sell_threshold_spin.setValue(result.optimal_sell_threshold * 100)

        # 保存优化结果
        self.current_strategy_result = result.optimal_result

        # 在图表上标记买卖点
        self.chart.draw_trades(result.optimal_result)

        # 显示结果
        result_text = format_optimization_result(result)
        self.result_text.setPlainText(result_text)

        self.status.showMessage(
            f"优化完成：最优买入{result.optimal_buy_threshold*100:.1f}%，"
            f"卖出{result.optimal_sell_threshold*100:.1f}%，"
            f"收益率{result.max_return_rate*100:+.2f}%"
        )

    def _on_optimize_failed(self, message: str) -> None:
        """优化失败回调"""
        self.status.showMessage("优化失败")
        QMessageBox.warning(self, "优化失败", message)
        self.result_text.setPlainText(f"优化失败: {message}")

    def _cleanup_optimizer_thread(self) -> None:
        """清理优化器线程"""
        self.calc_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        if self.optimizer_thread is not None:
            self.optimizer_thread.quit()
            self.optimizer_thread.wait(1000)
            self.optimizer_thread.deleteLater()
            self.optimizer_thread = None
        if self.optimizer_worker is not None:
            self.optimizer_worker.deleteLater()
            self.optimizer_worker = None


# 导入 pandas 用于日期计算
import pandas as pd
