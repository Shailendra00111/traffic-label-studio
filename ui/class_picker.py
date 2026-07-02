"""
ui/class_picker.py
====================
Small popup dialog shown right after a shape (rectangle or polygon) is
finished being drawn. Lets the user pick which class it belongs to, or
add a brand-new class on the spot.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QWidget, QMessageBox,
)

from core.annotation import CLASSES, CLASS_COLORS, add_custom_class

DARK_STYLESHEET = """
QDialog { background-color: #1e1e1e; }
QLabel { color: #d4d4d4; }
QLabel#title { font-size: 13pt; font-weight: bold; color: #ffffff; }
QPushButton.classBtn {
    background-color: #2d2d30; color: #d4d4d4; border: 1px solid #3c3c3c;
    border-radius: 4px; padding: 8px; text-align: left; font-size: 10pt;
}
QPushButton.classBtn:hover { background-color: #0e639c; border: 1px solid #0e639c; }
QLineEdit {
    background-color: #2d2d30; color: #d4d4d4; border: 1px solid #3c3c3c;
    border-radius: 4px; padding: 6px;
}
QLineEdit:focus { border: 1px solid #0e639c; }
QPushButton#addBtn {
    background-color: #0e639c; color: white; border: none;
    border-radius: 4px; padding: 6px 12px; font-weight: bold;
}
QPushButton#addBtn:hover { background-color: #1177bb; }
"""


class ClassPickerDialog(QDialog):
    """Modal popup: pick a class for the shape just drawn, or add a new one."""

    def __init__(self, parent=None, default_class_id: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Select class")
        self.setFixedSize(300, 420)
        self.setStyleSheet(DARK_STYLESHEET)

        self.selected_class_id = default_class_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("What is this?")
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel("Pick a class for the shape you just drew.")
        subtitle.setStyleSheet("color:#8a8a8a; font-size:9pt;")
        layout.addWidget(subtitle)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none;")
        layout.addWidget(self.scroll, 1)

        self._build_class_buttons()

        layout.addWidget(self._divider())

        add_row = QHBoxLayout()
        self.new_class_input = QLineEdit()
        self.new_class_input.setPlaceholderText("Add new class…")
        self.new_class_input.returnPressed.connect(self._add_class)
        add_row.addWidget(self.new_class_input)
        add_btn = QPushButton("+")
        add_btn.setObjectName("addBtn")
        add_btn.setFixedWidth(32)
        add_btn.clicked.connect(self._add_class)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

    @staticmethod
    def _divider():
        line = QLabel()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color:#3c3c3c;")
        return line

    def _build_class_buttons(self):
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        for i, cls in enumerate(CLASSES):
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(
                f"background-color:{CLASS_COLORS[i]}; border:1px solid #3c3c3c; "
                f"border-radius:2px;")

            btn = QPushButton(f"{i + 1}. {cls}" if i < 9 else cls)
            btn.setProperty("class", "classBtn")
            btn.setStyleSheet(
                "QPushButton { background-color: #2d2d30; color: #d4d4d4; "
                "border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px; "
                "text-align: left; font-size: 10pt; } "
                "QPushButton:hover { background-color: #0e639c; border: 1px solid #0e639c; }"
            )
            btn.clicked.connect(lambda checked, idx=i: self._choose(idx))

            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addWidget(swatch)
            wrapper_layout.addWidget(btn, 1)
            vbox.addWidget(wrapper)

        vbox.addStretch()
        self.scroll.setWidget(container)

    def _choose(self, class_id: int):
        self.selected_class_id = class_id
        self.accept()

    def _add_class(self):
        name = self.new_class_input.text()
        success, message = add_custom_class(name)
        if success:
            self.new_class_input.clear()
            self._build_class_buttons()
            # auto-select the newly added class
            self._choose(len(CLASSES) - 1)
        else:
            QMessageBox.warning(self, "Cannot add class", message)