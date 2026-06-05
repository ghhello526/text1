"""左侧基金列表面板 — 显示所有基金的信号灯摘要"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.models import Fund, Position, SignalAction, TradingSignal

# 信号灯颜色映射
_SIGNAL_COLORS = {
    SignalAction.BUY: ("#22c55e", "买入"),
    SignalAction.SELL: ("#ef4444", "卖出"),
    SignalAction.HOLD: ("#f59e0b", "持有"),
}
_DEFAULT_COLOR = ("#9ca3af", "未建仓")

MAX_FUNDS = 6


class FundCard(QFrame):
    """单只基金卡片"""

    clicked = pyqtSignal(int)  # fund_id

    def __init__(self, fund: Fund, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.fund_id = fund.id
        self._selected = False
        self._setup_ui(fund)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _setup_ui(self, fund: Fund) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(72)
        self.setStyleSheet(self._normal_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 第一行：信号灯 + 基金名称
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.signal_dot = QLabel("●")
        self.signal_dot.setFont(QFont("Microsoft YaHei", 14))
        self.signal_dot.setFixedWidth(20)
        self.signal_dot.setStyleSheet("color: #9ca3af;")
        top_row.addWidget(self.signal_dot)

        self.name_label = QLabel(fund.name or fund.code)
        self.name_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        top_row.addWidget(self.name_label, stretch=1)

        self.signal_text = QLabel("未建仓")
        self.signal_text.setFont(QFont("Microsoft YaHei", 8))
        self.signal_text.setStyleSheet("color: #6b7280;")
        top_row.addWidget(self.signal_text)

        layout.addLayout(top_row)

        # 第二行：净值 + 仓位进度条
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.nav_label = QLabel("净值: --")
        self.nav_label.setFont(QFont("Microsoft YaHei", 8))
        self.nav_label.setStyleSheet("color: #6b7280;")
        bottom_row.addWidget(self.nav_label)

        self.position_bar = QProgressBar()
        self.position_bar.setRange(0, 100)
        self.position_bar.setValue(0)
        self.position_bar.setFixedHeight(12)
        self.position_bar.setFixedWidth(80)
        self.position_bar.setFormat("%v%")
        self.position_bar.setFont(QFont("Microsoft YaHei", 7))
        bottom_row.addWidget(self.position_bar)

        layout.addLayout(bottom_row)

    def update_signal(self, signal: TradingSignal) -> None:
        """更新信号灯显示"""
        color, text = _SIGNAL_COLORS.get(signal.action, _DEFAULT_COLOR)
        self.signal_dot.setStyleSheet(f"color: {color};")
        self.signal_text.setText(text)
        if signal.current_nav > 0:
            self.nav_label.setText(f"净值: {signal.current_nav:.4f}")
        pct = int(signal.position_pct * 100)
        self.position_bar.setValue(min(pct, 100))

    def update_position(self, position: Position, nav: float = 0.0) -> None:
        """用持仓数据更新显示（无信号时）"""
        if nav > 0:
            self.nav_label.setText(f"净值: {nav:.4f}")
        if position.total_shares > 0:
            self.signal_text.setText(position.current_strategy)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setStyleSheet(self._selected_style() if selected else self._normal_style())

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.fund_id)
        super().mousePressEvent(event)

    @staticmethod
    def _normal_style() -> str:
        return """
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }
            QFrame:hover {
                border-color: #3b82f6;
                background-color: #f0f9ff;
            }
        """

    @staticmethod
    def _selected_style() -> str:
        return """
            QFrame {
                background-color: #eff6ff;
                border: 2px solid #3b82f6;
                border-radius: 8px;
            }
        """


class FundListPanel(QWidget):
    """左侧基金列表面板"""

    fund_selected = pyqtSignal(int)  # fund_id
    add_fund_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(220)
        self._cards: dict[int, FundCard] = {}
        self._selected_fund_id: int | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题
        self.title_label = QLabel("我的基金 (0/6)")
        self.title_label.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.title_label.setContentsMargins(8, 8, 8, 0)
        layout.addWidget(self.title_label)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(8, 4, 8, 4)
        self.cards_layout.setSpacing(6)
        self.cards_layout.addStretch()

        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll, stretch=1)

        # 底部按钮
        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(8, 0, 8, 8)
        btn_layout.setSpacing(6)

        self.add_btn = QPushButton("+ 添加基金")
        self.add_btn.setFixedHeight(32)
        self.add_btn.setFont(QFont("Microsoft YaHei", 9))
        self.add_btn.clicked.connect(self.add_fund_requested.emit)
        btn_layout.addWidget(self.add_btn)

        self.settings_btn = QPushButton("⚙ 资金设置")
        self.settings_btn.setFixedHeight(32)
        self.settings_btn.setFont(QFont("Microsoft YaHei", 9))
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        btn_layout.addWidget(self.settings_btn)

        layout.addLayout(btn_layout)

    def add_fund_card(self, fund: Fund) -> None:
        """添加一只基金卡片"""
        if fund.id in self._cards:
            return
        card = FundCard(fund)
        card.clicked.connect(self._on_card_clicked)
        self._cards[fund.id] = card
        # 插入到 stretch 前面
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._update_title()

    def remove_fund_card(self, fund_id: int) -> None:
        """移除基金卡片"""
        card = self._cards.pop(fund_id, None)
        if card:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
            self._update_title()

    def update_fund_signal(self, fund_id: int, signal: TradingSignal) -> None:
        """更新某只基金的信号灯"""
        card = self._cards.get(fund_id)
        if card:
            card.update_signal(signal)

    def update_all_signals(self, signals: dict[int, TradingSignal]) -> None:
        """批量更新所有信号"""
        for fund_id, signal in signals.items():
            self.update_fund_signal(fund_id, signal)

    def clear_all(self) -> None:
        """清除所有卡片"""
        for card in list(self._cards.values()):
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._update_title()

    def get_selected_fund_id(self) -> int | None:
        return self._selected_fund_id

    def _on_card_clicked(self, fund_id: int) -> None:
        # 取消之前选中
        if self._selected_fund_id and self._selected_fund_id in self._cards:
            self._cards[self._selected_fund_id].set_selected(False)
        # 选中新的
        self._selected_fund_id = fund_id
        if fund_id in self._cards:
            self._cards[fund_id].set_selected(True)
        self.fund_selected.emit(fund_id)

    def _update_title(self) -> None:
        self.title_label.setText(f"我的基金 ({len(self._cards)}/{MAX_FUNDS})")
