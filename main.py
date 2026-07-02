#!/usr/bin/env python3
"""
Traffic Label Studio (PyQt5 edition)
=====================================
Shows a Login/Register screen first. Only after a successful login does
the main annotation tool open.

Run:
    pip install PyQt5
    python main.py
"""

import sys
from PyQt5.QtWidgets import QApplication, QDialog

from ui.login_window import LoginWindow
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    login = LoginWindow()
    result = login.exec_()  # blocks until login window closes

    if result != QDialog.Accepted:
        # User closed the login window without logging in
        sys.exit(0)

    window = MainWindow(username=login.username)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()