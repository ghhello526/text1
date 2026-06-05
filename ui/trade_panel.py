"""模式A：实时交易辅助面板 — 信号灯 + 操作计划 + 交易记录"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.models import SignalAction, TradingSignal, Trade

_ACTION_STYLES = {
    SignalAction.BUY: ("建议买入", "#22c55e", "#f0fdf4"),
    SignalAction.SELL: ("建议卖出", "#ef4444", "#fef2f2"),
    SignalAction.HOLD: ("持有观望", "#f59e0b", "#fffbeb"),
}


class TradePanel(QWidget):
    """实时交易辅助面板（模式A右侧）"""

    confirm_trade = pyqtSignal()  # 确认操作信号
    skip_trade = pyqtSignal()    # 跳过操作信号

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_signal: TradingSignal | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ===== ① 信号灯区 =====
        self.signal_group = QGroupBox("交易信号")
        self.signal_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        signal_layout = QVBoxLayout(self.signal_group)
        signal_layout.setSpacing(8)

        # 信号灯大标题
        self.signal_label = QLabel("等待数据...")
        self.signal_label.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        self.signal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.signal_label.setFixedHeight(48)
        self.signal_label.setStyleSheet(
            "background-color: #f3f4f6; border-radius: 8px; color: #6b7280;"
        )
        signal_layout.addWidget(self.signal_label)

        # 策略+区间信息
        info_row = QHBoxLayout()
        self.strategy_label = QLabel("策略: --")
        self.strategy_label.setFont(QFont("Microsoft YaHei", 9))
        info_row.addWidget(self.strategy_label)

        self.zone_label = QLabel("区间: --")
        self.zone_label.setFont(QFont("Microsoft YaHei", 9))
        info_row.addWidget(self.zone_label)
        signal_layout.addLayout(info_row)

        # 数值行
        values_row = QHBoxLayout()
        self.nav_label = QLabel("净值: --")
        self.nav_label.setFont(QFont("Microsoft YaHei", 9))
        values_row.addWidget(self.nav_label)

        self.anchor_label = QLabel("锚点: --")
        self.anchor_label.setFont(QFont("Microsoft YaHei", 9))
        values_row.addWidget(self.anchor_label)

        self.position_label = QLabel("仓位: --")
        self.position_label.setFont(QFont("Microsoft YaHei", 9))
        values_row.addWidget(self.position_label)
        signal_layout.addLayout(values_row)

        layout.addWidget(self.signal_group)

        # ===== ② 操作计划区 =====
        self.plan_group = QGroupBox("操作计划")
        self.plan_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        plan_layout = QVBoxLayout(self.plan_group)
        plan_layout.setSpacing(8)

        self.suggestion_label = QLabel("等待信号...")
        self.suggestion_label.setFont(QFont("Microsoft YaHei", 10))
        self.suggestion_label.setWordWrap(True)
        plan_layout.addWidget(self.suggestion_label)

        self.reason_label = QLabel("")
        self.reason_label.setFont(QFont("Microsoft YaHei", 9))
        self.reason_label.setStyleSheet("color: #6b7280;")
        self.reason_label.setWordWrap(True)
        plan_layout.addWidget(self.reason_label)

        # 下一触发条件
        self.next_trigger_label = QLabel("")
        self.next_trigger_label.setFont(QFont("Microsoft YaHei", 9))
        self.next_trigger_label.setStyleSheet("color: #4b5563;")
        self.next_trigger_label.setWordWrap(True)
        plan_layout.addWidget(self.next_trigger_label)

        # 按钮行
        btn_row = QHBoxLayout()
        self.confirm_btn = QPushButton("✓ 确认已操作")
        self.confirm_btn.setFixedHeight(36)
        self.confirm_btn.setFont(QFont("Microsoft YaHei", 10))
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet(
            "QPushButton { background-color: #22c55e; color: white; border-radius: 6px; }"
            "QPushButton:disabled { background-color: #d1d5db; }"
            "QPushButton:hover { background-color: #16a34a; }"
        )
        self.confirm_btn.clicked.connect(self.confirm_trade.emit)
        btn_row.addWidget(self.confirm_btn)

        self.skip_btn = QPushButton("跳过本次")
        self.skip_btn.setFixedHeight(36)
        self.skip_btn.setFont(QFont("Microsoft YaHei", 10))
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self.skip_trade.emit)
        btn_row.addWidget(self.skip_btn)

        plan_layout.addLayout(btn_row)
        layout.addWidget(self.plan_group)

        # ===== ③ 交易记录区 =====
        self.trades_group = QGroupBox("交易记录")
        self.trades_group.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        trades_layout = QVBoxLayout(self.trades_group)

        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(5)
        self.trades_table.setHorizontalHeaderLabels(["日期", "类型", "金额", "净值", "策略"])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trades_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trades_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades_table.setAlternatingRowColors(True)
        self.trades_table.setFont(QFont("Microsoft YaHei", 9))
        trades_layout.addWidget(self.trades_table)

        layout.addWidget(self.trades_group, stretch=1)

    def update_signal(self, signal: TradingSignal) -> None:
        """更新面板显示"""
        self._current_signal = signal

        # 更新信号灯
        action_text, color, bg_color = _ACTION_STYLES.get(
            signal.action, ("持有观望", "#f59e0b", "#fffbeb")
        )
        self.signal_label.setText(action_text)
        self.signal_label.setStyleSheet(
            f"background-color: {bg_color}; border-radius: 8px; color: {color};"
        )

        # 策略和区间
        strategy_names = {
            "build": "建仓策略", "swing": "波动策略",
            "take_profit": "止盈策略", "none": "无",
        }
        zone_names = {
            "undervalued": "低估区(机会线下)",
            "fair": "合理区(机会~中位)",
            "overvalued": "偏高区(中位~危险)",
            "bubble": "泡沫区(危险线上)",
        }
        self.strategy_label.setText(f"策略: {strategy_names.get(signal.strategy.value, '--')}")
        self.zone_label.setText(f"区间: {zone_names.get(signal.zone.value, '--')}")

        # 数值
        self.nav_label.setText(f"净值: {signal.current_nav:.4f}" if signal.current_nav > 0 else "净值: --")
        self.anchor_label.setText(f"锚点: {signal.anchor_nav:.4f}" if signal.anchor_nav > 0 else "锚点: --")
        self.position_label.setText(f"仓位: {signal.position_pct*100:.1f}%")

        # 操作建议
        if signal.action == SignalAction.BUY:
            self.suggestion_label.setText(f"建议买入 {signal.suggested_amount:.0f} 元")
        elif signal.action == SignalAction.SELL:
            self.suggestion_label.setText(f"建议卖出 {signal.suggested_amount:.0f} 元")
        else:
            self.suggestion_label.setText("暂无操作建议，继续持有")

        self.reason_label.setText(f"触发原因: {signal.trigger_reason}")

        # 下一触发
        triggers = []
        if signal.next_trigger_up > 0:
            triggers.append(f"↑ 涨至 {signal.next_trigger_up:.4f} → 卖出信号")
        if signal.next_trigger_down > 0:
            triggers.append(f"↓ 跌至 {signal.next_trigger_down:.4f} → 买入信号")
        self.next_trigger_label.setText("\n".join(triggers) if triggers else "")

        # 按钮状态
        has_action = signal.action in (SignalAction.BUY, SignalAction.SELL)
        self.confirm_btn.setEnabled(has_action)
        self.skip_btn.setEnabled(has_action)

    def update_trades(self, trades: list[Trade]) -> None:
        """更新交易记录表格"""
        self.trades_table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            self.trades_table.setItem(row, 0, QTableWidgetItem(trade.trade_date))
            self.trades_table.setItem(row, 1, QTableWidgetItem(trade.trade_type))
            self.trades_table.setItem(row, 2, QTableWidgetItem(f"{trade.amount:.0f}"))
            self.trades_table.setItem(row, 3, QTableWidgetItem(f"{trade.nav:.4f}"))
            self.trades_table.setItem(row, 4, QTableWidgetItem(trade.strategy_type))

    def get_current_signal(self) -> TradingSignal | None:
        return self._current_signal

    def clear(self) -> None:
        """清空面板"""
        self.signal_label.setText("等待数据...")
        self.signal_label.setStyleSheet(
            "background-color: #f3f4f6; border-radius: 8px; color: #6b7280;"
        )
        self.strategy_label.setText("策略: --")
        self.zone_label.setText("区间: --")
        self.nav_label.setText("净值: --")
        self.anchor_label.setText("锚点: --")
        self.position_label.setText("仓位: --")
        self.suggestion_label.setText("等待信号...")
        self.reason_label.setText("")
        self.next_trigger_label.setText("")
        self.confirm_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.trades_table.setRowCount(0)
        self._current_signal = None
