"""
ui/login_window.py
====================
Login / Register dialog shown before the main annotation tool opens.
On successful login, self.username holds the logged-in user's name and
the dialog is accepted (QDialog.Accepted) — main.py checks this before
launching MainWindow.

Login uses the same Supabase account as the AnnotateX website — the
same username/email/password works in both places.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFrame, QMessageBox,
)

from core.auth import register_user, login_user

DARK_STYLESHEET = """
QDialog { background-color: #1e1e1e; }
QLabel { color: #d4d4d4; }
QLabel#title { font-size: 18pt; font-weight: bold; color: #ffffff; }
QLabel#subtitle { color: #8a8a8a; font-size: 9pt; }
QLabel#error { color: #e74c3c; font-size: 9pt; }
QLabel#success { color: #2ecc71; font-size: 9pt; }
QLineEdit {
    background-color: #2d2d30; color: #d4d4d4; border: 1px solid #3c3c3c;
    border-radius: 4px; padding: 8px; font-size: 10pt;
}
QLineEdit:focus { border: 1px solid #0e639c; }
QPushButton {
    background-color: #0e639c; color: white; border: none;
    padding: 10px; border-radius: 4px; font-weight: bold; font-size: 10pt;
}
QPushButton:hover { background-color: #1177bb; }
QPushButton#link {
    background-color: transparent; color: #4fa8e0; font-weight: normal;
    text-decoration: underline; padding: 4px;
}
QPushButton#link:hover { background-color: transparent; color: #6fc0f5; }
"""


class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AnnotateX — Login")
        self.setFixedSize(380, 480)
        self.setStyleSheet(DARK_STYLESHEET)

        self.username: str = ""
        self.mode = "login"  # "login" or "register"

        self._build_ui()

    # ------------------------------------------------------------- UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(6)

        self.title_label = QLabel("Welcome back")
        self.title_label.setObjectName("title")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Log in to AnnotateX")
        self.subtitle_label.setObjectName("subtitle")
        layout.addWidget(self.subtitle_label)

        layout.addSpacing(18)

        layout.addWidget(QLabel("Username"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        layout.addWidget(self.username_input)

        layout.addSpacing(8)

        # Email — only shown/required in register mode, since Supabase
        # authenticates by email under the hood.
        self.email_label = QLabel("Email")
        layout.addWidget(self.email_label)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter email")
        layout.addWidget(self.email_input)
        self.email_label.hide()
        self.email_input.hide()

        layout.addSpacing(8)

        layout.addWidget(QLabel("Password"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.password_input)

        layout.addSpacing(6)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        layout.addSpacing(10)

        self.submit_button = QPushButton("Log In")
        self.submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_button)

        layout.addSpacing(4)

        toggle_row = QHBoxLayout()
        self.toggle_label = QLabel("Don't have an account?")
        self.toggle_label.setObjectName("subtitle")
        toggle_row.addWidget(self.toggle_label)
        toggle_row.addStretch()
        self.toggle_button = QPushButton("Register")
        self.toggle_button.setObjectName("link")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self._toggle_mode)
        toggle_row.addWidget(self.toggle_button)
        layout.addLayout(toggle_row)

        layout.addStretch()

    # ---------------------------------------------------------- logic
    def _toggle_mode(self):
        self.mode = "register" if self.mode == "login" else "login"
        self.message_label.setText("")
        self.message_label.setObjectName("")
        self.message_label.setStyleSheet("")

        if self.mode == "register":
            self.title_label.setText("Create account")
            self.subtitle_label.setText("Register a new username, email and password")
            self.submit_button.setText("Register")
            self.toggle_label.setText("Already have an account?")
            self.toggle_button.setText("Log In")
            self.email_label.show()
            self.email_input.show()
        else:
            self.title_label.setText("Welcome back")
            self.subtitle_label.setText("Log in to AnnotateX")
            self.submit_button.setText("Log In")
            self.toggle_label.setText("Don't have an account?")
            self.toggle_button.setText("Register")
            self.email_label.hide()
            self.email_input.hide()

    def _set_message(self, text: str, error: bool):
        self.message_label.setText(text)
        self.message_label.setStyleSheet(
            "color: #e74c3c; font-size: 9pt;" if error else "color: #2ecc71; font-size: 9pt;"
        )

    def _on_submit(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if self.mode == "login":
            result = login_user(username, password)
            if result.success:
                self.username = username
                self.accept()
            else:
                self._set_message(result.message, error=True)
        else:
            email = self.email_input.text().strip()
            result = register_user(username, email, password)
            if result.success:
                self._set_message(
                    "Account created! You can now log in.", error=False)
                self._toggle_mode()
                self.username_input.setText(username)
                self.password_input.clear()
                self.password_input.setFocus()
            else:
                self._set_message(result.message, error=True)