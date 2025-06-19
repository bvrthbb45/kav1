import sys
import os
from PySide6.QtWidgets import QApplication
from app.views.main_window import MainWindow


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    with open(resource_path("style.css"), "r") as f:
        _style = f.read()
        app.setStyleSheet(_style)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
