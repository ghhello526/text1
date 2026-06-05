"""主窗口 — 守基宝交易辅助系统"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from services.database import DatabaseManager
from services.fund_service import FundDataError, FundService
from services.models import Fund, SignalAction, TradingSignal
from services.signal_generator import SignalGenerator
from ui.backtest_panel import BacktestPanel
from ui.fund_list_panel import FundListPanel, MAX_FUNDS
from ui.trade_panel import TradePanel


class SignalRefreshWorker(QObject):
    """后台刷新所有基金信号"""

    finished = pyqtSignal(object)  # dict[int, TradingSignal]
    failed = pyqtSignal(str)

    def __init__(self, signal_gen: SignalGenerator) -> None:
        super().__init__()
        self.signal_gen = signal_gen

    def run(self) -> None:
        try:
            signals = self.signal_gen.refresh_all_signals()
            self.finished.emit(signals)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    """守基宝交易辅助系统主窗口"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("守基宝 4% 定投法 — 交易辅助系统")
        self.resize(1400, 850)
        self.setMinimumSize(1100, 700)

        # 服务实例
        self.db = DatabaseManager()
        self.fund_service = FundService()
        self.signal_gen = SignalGenerator(db=self.db, fund_service=self.fund_service)

        # 当前状态
        self._current_mode = "trade"  # "trade" or "backtest"
        self._signals: dict[int, TradingSignal] = {}
        self._refresh_thread: QThread | None = None
        self._refresh_worker: SignalRefreshWorker | None = None

        # 构建UI
        self._build_ui()
        # 加载数据
        self._load_funds()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 顶部工具栏 =====
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("background-color: #1e293b;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 8, 16, 8)
        toolbar_layout.setSpacing(12)

        # 应用标题
        title = QLabel("守基宝")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #f8fafc;")
        toolbar_layout.addWidget(title)

        toolbar_layout.addSpacing(24)

        # 模式切换按钮
        self.trade_btn = QPushButton("实时交易")
        self.trade_btn.setFixedSize(100, 34)
        self.trade_btn.setFont(QFont("Microsoft YaHei", 10))
        self.trade_btn.setCheckable(True)
        self.trade_btn.setChecked(True)
        self.trade_btn.clicked.connect(lambda: self._switch_mode("trade"))
        toolbar_layout.addWidget(self.trade_btn)

        self.backtest_btn = QPushButton("策略回测")
        self.backtest_btn.setFixedSize(100, 34)
        self.backtest_btn.setFont(QFont("Microsoft YaHei", 10))
        self.backtest_btn.setCheckable(True)
        self.backtest_btn.clicked.connect(lambda: self._switch_mode("backtest"))
        toolbar_layout.addWidget(self.backtest_btn)

        toolbar_layout.addStretch()

        # 刷新按钮
        self.refresh_btn = QPushButton("刷新信号")
        self.refresh_btn.setFixedSize(90, 34)
        self.refresh_btn.setFont(QFont("Microsoft YaHei", 9))
        self.refresh_btn.clicked.connect(self._refresh_signals)
        toolbar_layout.addWidget(self.refresh_btn)

        self._update_toolbar_style()
        main_layout.addWidget(toolbar)

        # ===== 主体：左右分栏 =====
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(8)

        splitter = QSplitter()
        body_layout.addWidget(splitter)

        # 左侧基金列表
        self.fund_list = FundListPanel()
        self.fund_list.fund_selected.connect(self._on_fund_selected)
        self.fund_list.add_fund_requested.connect(self._add_fund_dialog)
        self.fund_list.settings_requested.connect(self._settings_dialog)
        splitter.addWidget(self.fund_list)

        # 右侧面板栈
        self.panel_stack = QStackedWidget()
        self.trade_panel = TradePanel()
        self.trade_panel.confirm_trade.connect(self._on_confirm_trade)
        self.trade_panel.skip_trade.connect(self._on_skip_trade)
        self.panel_stack.addWidget(self.trade_panel)  # index 0

        self.backtest_panel = BacktestPanel()
        self.panel_stack.addWidget(self.backtest_panel)  # index 1

        splitter.addWidget(self.panel_stack)
        splitter.setSizes([220, 1100])

        main_layout.addWidget(body, stretch=1)

        # 状态栏
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪")

    def _update_toolbar_style(self) -> None:
        """更新工具栏按钮的选中样式"""
        active_style = (
            "QPushButton { background-color: #3b82f6; color: white; "
            "border-radius: 6px; border: none; }"
        )
        inactive_style = (
            "QPushButton { background-color: #334155; color: #94a3b8; "
            "border-radius: 6px; border: none; }"
            "QPushButton:hover { background-color: #475569; color: white; }"
        )
        self.trade_btn.setStyleSheet(active_style if self._current_mode == "trade" else inactive_style)
        self.backtest_btn.setStyleSheet(active_style if self._current_mode == "backtest" else inactive_style)

    # ==================== 模式切换 ====================

    def _switch_mode(self, mode: str) -> None:
        self._current_mode = mode
        self.trade_btn.setChecked(mode == "trade")
        self.backtest_btn.setChecked(mode == "backtest")
        self._update_toolbar_style()

        if mode == "trade":
            self.panel_stack.setCurrentIndex(0)
        else:
            self.panel_stack.setCurrentIndex(1)

        # 如果有选中的基金，切换面板内容
        fund_id = self.fund_list.get_selected_fund_id()
        if fund_id:
            self._on_fund_selected(fund_id)

    # ==================== 数据加载 ====================

    def _load_funds(self) -> None:
        """从数据库加载所有基金到左侧列表"""
        funds = self.db.get_all_funds()
        self.fund_list.clear_all()
        for fund in funds:
            self.fund_list.add_fund_card(fund)

    # ==================== 信号刷新 ====================

    def _refresh_signals(self) -> None:
        """后台刷新所有基金的信号"""
        if self._refresh_thread and self._refresh_thread.isRunning():
            return

        self.refresh_btn.setEnabled(False)
        self.status.showMessage("正在刷新信号...")

        self._refresh_thread = QThread(self)
        self._refresh_worker = SignalRefreshWorker(self.signal_gen)
        self._refresh_worker.moveToThread(self._refresh_thread)

        self._refresh_thread.started.connect(self._refresh_worker.run)
        self._refresh_worker.finished.connect(self._on_signals_refreshed)
        self._refresh_worker.failed.connect(self._on_signals_failed)
        self._refresh_worker.finished.connect(self._cleanup_refresh)
        self._refresh_worker.failed.connect(self._cleanup_refresh)
        self._refresh_thread.start()

    def _on_signals_refreshed(self, signals: dict[int, TradingSignal]) -> None:
        self._signals = signals
        self.fund_list.update_all_signals(signals)
        self.status.showMessage(f"信号刷新完成，共 {len(signals)} 只基金")

        # 如果当前有选中基金且在交易模式，更新面板
        fund_id = self.fund_list.get_selected_fund_id()
        if fund_id and fund_id in signals and self._current_mode == "trade":
            self.trade_panel.update_signal(signals[fund_id])
            trades = self.db.get_trades(fund_id)
            self.trade_panel.update_trades(trades)

    def _on_signals_failed(self, msg: str) -> None:
        self.status.showMessage(f"信号刷新失败: {msg}")

    def _cleanup_refresh(self) -> None:
        self.refresh_btn.setEnabled(True)
        if self._refresh_thread:
            self._refresh_thread.quit()
            self._refresh_thread.wait(1000)
            self._refresh_thread.deleteLater()
            self._refresh_thread = None
        if self._refresh_worker:
            self._refresh_worker.deleteLater()
            self._refresh_worker = None

    # ==================== 基金选中 ====================

    def _on_fund_selected(self, fund_id: int) -> None:
        """用户点击了某只基金"""
        fund = self.db.get_fund(fund_id)
        if fund is None:
            return

        if self._current_mode == "trade":
            # 更新交易面板
            signal = self._signals.get(fund_id)
            if signal:
                self.trade_panel.update_signal(signal)
            else:
                self.trade_panel.clear()
            trades = self.db.get_trades(fund_id)
            self.trade_panel.update_trades(trades)
        else:
            # 更新回测面板
            self.backtest_panel.set_fund(fund)

        self.status.showMessage(f"已选中: {fund.name} ({fund.code})")

    # ==================== 确认交易 ====================

    def _on_confirm_trade(self) -> None:
        """用户点击确认操作"""
        fund_id = self.fund_list.get_selected_fund_id()
        signal = self.trade_panel.get_current_signal()
        if not fund_id or not signal:
            return

        try:
            self.signal_gen.confirm_trade(fund_id, signal)
            self.status.showMessage("交易已确认并记录")
            # 刷新
            trades = self.db.get_trades(fund_id)
            self.trade_panel.update_trades(trades)
            # 重新生成信号
            new_signal = self.signal_gen.generate_signal(fund_id)
            self._signals[fund_id] = new_signal
            self.trade_panel.update_signal(new_signal)
            self.fund_list.update_fund_signal(fund_id, new_signal)
        except Exception as exc:
            QMessageBox.warning(self, "操作失败", str(exc))

    def _on_skip_trade(self) -> None:
        """用户点击跳过"""
        self.status.showMessage("已跳过本次操作建议")

    # ==================== 添加基金 ====================

    def _add_fund_dialog(self) -> None:
        """弹出添加基金对话框"""
        if self.db.get_fund_count() >= MAX_FUNDS:
            QMessageBox.warning(self, "上限提示", f"最多支持 {MAX_FUNDS} 只基金")
            return

        code, ok = QInputDialog.getText(
            self, "添加基金", "请输入6位基金代码:",
        )
        if not ok or not code:
            return

        code = code.strip()
        if len(code) != 6 or not code.isdigit():
            QMessageBox.warning(self, "格式错误", "请输入正确的6位数字基金代码")
            return

        # 检查是否已存在
        if self.db.get_fund_by_code(code):
            QMessageBox.warning(self, "重复添加", f"基金 {code} 已存在")
            return

        # 查询基金名称
        self.status.showMessage(f"正在查询基金 {code}...")
        try:
            history = self.fund_service.get_fund_history(code)
            name = history.name
        except FundDataError:
            name = code

        # 弹出三线设置对话框
        dialog = FundConfigDialog(code, name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            fund = dialog.get_fund()
            fund_id = self.db.add_fund(fund)
            fund.id = fund_id
            self.fund_list.add_fund_card(fund)
            self.status.showMessage(f"已添加: {fund.name} ({fund.code})")

    # ==================== 资金设置 ====================

    def _settings_dialog(self) -> None:
        """资金设置对话框"""
        QMessageBox.information(
            self, "资金设置",
            "此功能用于设置年龄、总可投资产等。\n"
            "目前可通过每只基金的'每份金额×总份数'来控制资金分配。"
        )


class FundConfigDialog(QDialog):
    """基金配置对话框（添加时设定三线）"""

    def __init__(self, code: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"配置基金 - {name} ({code})")
        self.setFixedWidth(400)
        self._code = code
        self._name = name
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.name_edit = QLineEdit(self._name)
        layout.addRow("基金名称:", self.name_edit)

        self.opportunity_spin = QDoubleSpinBox()
        self.opportunity_spin.setRange(0.01, 99.99)
        self.opportunity_spin.setDecimals(4)
        self.opportunity_spin.setValue(0.80)
        layout.addRow("机会线净值:", self.opportunity_spin)

        self.middle_spin = QDoubleSpinBox()
        self.middle_spin.setRange(0.01, 99.99)
        self.middle_spin.setDecimals(4)
        self.middle_spin.setValue(1.00)
        layout.addRow("中位线净值:", self.middle_spin)

        self.danger_spin = QDoubleSpinBox()
        self.danger_spin.setRange(0.01, 99.99)
        self.danger_spin.setDecimals(4)
        self.danger_spin.setValue(1.20)
        layout.addRow("危险线净值:", self.danger_spin)

        self.main_ratio_spin = QDoubleSpinBox()
        self.main_ratio_spin.setRange(10, 90)
        self.main_ratio_spin.setValue(60)
        self.main_ratio_spin.setSuffix("%")
        layout.addRow("主仓占比:", self.main_ratio_spin)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(100, 100000)
        self.amount_spin.setValue(1250)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSuffix(" 元")
        layout.addRow("每份金额:", self.amount_spin)

        self.shares_spin = QDoubleSpinBox()
        self.shares_spin.setRange(5, 20)
        self.shares_spin.setValue(10)
        self.shares_spin.setDecimals(0)
        layout.addRow("总份数:", self.shares_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_fund(self) -> Fund:
        main_ratio = self.main_ratio_spin.value() / 100.0
        return Fund(
            code=self._code,
            name=self.name_edit.text() or self._name,
            fund_type="自定义",
            main_ratio=main_ratio,
            swing_ratio=1.0 - main_ratio,
            opportunity_line=self.opportunity_spin.value(),
            middle_line=self.middle_spin.value(),
            danger_line=self.danger_spin.value(),
            per_share_amount=self.amount_spin.value(),
            total_shares_count=int(self.shares_spin.value()),
        )
