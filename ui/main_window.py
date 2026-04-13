from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from services.fund_service import FundDataError, FundHistory, FundService
from ui.chart_widget import ChartWidget


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
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"未知错误：{exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("基金净值上位机")
        self.resize(1200, 700)
        self.setMinimumSize(980, 620)

        self.fund_service = FundService()
        self.query_thread: QThread | None = None
        self.worker: FundQueryWorker | None = None

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("请输入 6 位基金代码，例如 161725")
        self.code_input.setMaxLength(6)
        self.code_input.setFixedHeight(34)
        self.code_input.setFont(QFont("Microsoft YaHei", 10))
        self.code_input.setText("161725")
        self.code_input.returnPressed.connect(self.query_fund)

        self.query_button = QPushButton("查询")
        self.query_button.setFixedHeight(34)
        self.query_button.setFont(QFont("Microsoft YaHei", 10))
        self.query_button.clicked.connect(self.query_fund)

        self.chart = ChartWidget()
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("就绪")

        self._build_layout()

    def _build_layout(self) -> None:
        container = QWidget(self)
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        label = QLabel("基金代码:")
        label.setFont(QFont("Microsoft YaHei", 10))
        top_bar.addWidget(label)
        top_bar.addWidget(self.code_input, stretch=1)
        top_bar.addWidget(self.query_button)

        root_layout.addLayout(top_bar)
        root_layout.addWidget(self.chart, stretch=1)

        container.setLayout(root_layout)
        self.setCentralWidget(container)

    def query_fund(self) -> None:
        if self.query_thread is not None and self.query_thread.isRunning():
            return

        code = self.code_input.text().strip()
        self.query_button.setEnabled(False)
        self.status.showMessage(f"正在查询基金 {code}...")

        self.query_thread = QThread(self)
        self.worker = FundQueryWorker(self.fund_service, code)
        self.worker.moveToThread(self.query_thread)

        self.query_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_query_success)
        self.worker.failed.connect(self._on_query_failed)
        self.worker.finished.connect(self._cleanup_query_thread)
        self.worker.failed.connect(self._cleanup_query_thread)
        self.query_thread.start()

    def _on_query_success(self, history: FundHistory) -> None:
        self.chart.draw_history(history.code, history.name, history.dataframe)
        self.status.showMessage(
            f"查询成功：{history.name} ({history.code})，共 {len(history.dataframe)} 条记录。"
        )

    def _on_query_failed(self, message: str) -> None:
        self.status.showMessage("查询失败")
        QMessageBox.warning(self, "查询失败", message)

    def _cleanup_query_thread(self) -> None:
        self.query_button.setEnabled(True)
        if self.query_thread is not None:
            self.query_thread.quit()
            self.query_thread.wait(1000)
            self.query_thread.deleteLater()
            self.query_thread = None
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
