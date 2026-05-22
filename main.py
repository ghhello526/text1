from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

print("当前运行的 Python 环境是:", sys.executable)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
