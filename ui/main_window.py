"""
ui/main_window.py
==================
Main application window: toolbar, class panel (with custom class add),
shape-type toggle (Rectangle / Polygon), ImageCanvas, shape list, file
list, status bar, progress bar.
"""

import os
import glob
import shutil

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QListWidget, QRadioButton, QButtonGroup, QFileDialog,
    QMessageBox, QProgressBar, QFrame, QShortcut, QLineEdit, QScrollArea,
)
from PyQt5.QtGui import QKeySequence

from core.image_canvas import ImageCanvas
from ui.class_picker import ClassPickerDialog
from core.annotation import (
    Shape, ImageState, CLASSES, CLASS_COLORS, add_custom_class,
    load_labels, save_labels, save_json_labels, label_path_for,
)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #1e1e1e; color: #d4d4d4; }
QFrame#panel { background-color: #252526; }
QLabel { color: #d4d4d4; }
QLabel#header { font-weight: bold; font-size: 11pt; padding: 4px 0; }
QLabel#muted { color: #8a8a8a; font-size: 9pt; }
QPushButton {
    background-color: #2d2d30; color: #d4d4d4; border: none;
    padding: 6px 10px; border-radius: 4px;
}
QPushButton:hover { background-color: #1177bb; }
QPushButton#accent { background-color: #0e639c; font-weight: bold; padding: 8px 12px; }
QPushButton#accent:hover { background-color: #1177bb; }
QPushButton:checked { background-color: #0e639c; }
QListWidget {
    background-color: #2d2d30; color: #d4d4d4; border: 1px solid #3c3c3c;
}
QListWidget::item:selected { background-color: #0e639c; color: white; }
QRadioButton { color: #d4d4d4; padding: 2px; }
QLineEdit {
    background-color: #2d2d30; color: #d4d4d4; border: 1px solid #3c3c3c;
    border-radius: 4px; padding: 5px;
}
QLineEdit:focus { border: 1px solid #0e639c; }
QProgressBar {
    background-color: #2d2d30; border: 1px solid #3c3c3c; border-radius: 3px;
    text-align: center; color: #d4d4d4;
}
QProgressBar::chunk { background-color: #0e639c; border-radius: 3px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, username: str = ""):
        super().__init__()
        self.username = username
        title = "Traffic Label Studio"
        if username:
            title += f"  —  Logged in as {username}"
        self.setWindowTitle(title)
        self.resize(1300, 820)
        self.setStyleSheet(DARK_STYLESHEET)

        self.folder = None
        self.image_paths = []
        self.current_index = -1
        self.states = {}  # path -> ImageState
        self.current_class = 0

        self._build_ui()
        self._build_shortcuts()

    # ------------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        root.addLayout(body, 1)

        body.addWidget(self._build_class_panel())

        # Center: image canvas
        center = QFrame()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(6, 6, 6, 6)

        self.image_label = ImageCanvas()
        self.image_label.setText("Open a folder to begin")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.shapesChanged.connect(self._on_shapes_changed)
        self.image_label.selectionChanged.connect(self._on_selection_changed)
        self.image_label.mouseMovedOnImage.connect(self._on_mouse_moved)
        self.image_label.shapeAwaitingClass.connect(self._on_shape_awaiting_class)
        center_layout.addWidget(self.image_label, 1)
        body.addWidget(center, 1)

        body.addWidget(self._build_right_panel())

        root.addWidget(self._build_status_bar())

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("panel")
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)

        def btn(text, slot, accent=False):
            b = QPushButton(text)
            if accent:
                b.setObjectName("accent")
            b.clicked.connect(slot)
            layout.addWidget(b)
            return b

        btn("📂 Open Folder", self.open_folder, accent=True)
        btn("⏮ Prev (A)", self.prev_image)
        btn("Next (D) ⏭", self.next_image)
        btn("↩ Undo (Ctrl+Z)", self.undo)
        btn("↪ Redo (Ctrl+Y)", self.redo)
        btn("🗑 Delete (Del)", self.delete_selected_box)

        # shape type toggle
        sep1 = QLabel("  |  ")
        sep1.setObjectName("muted")
        layout.addWidget(sep1)

        self.rect_button = QPushButton("▭ Rectangle")
        self.rect_button.setCheckable(True)
        self.rect_button.setChecked(True)
        self.rect_button.clicked.connect(lambda: self._set_shape_type("rect"))
        layout.addWidget(self.rect_button)

        self.polygon_button = QPushButton("⬠ Polygon")
        self.polygon_button.setCheckable(True)
        self.polygon_button.clicked.connect(lambda: self._set_shape_type("polygon"))
        layout.addWidget(self.polygon_button)

        sep2 = QLabel("  |  ")
        sep2.setObjectName("muted")
        layout.addWidget(sep2)

        btn("🔍+ (=)", lambda: self.image_label.apply_zoom(1.15))
        btn("🔍- (-)", lambda: self.image_label.apply_zoom(1 / 1.15))
        btn("Fit (0)", lambda: self.image_label.fit_to_window())
        layout.addStretch()
        btn("📦 Export Dataset", self.export_dataset)
        btn("💾 Save (Ctrl+S)", self.save_current, accent=True)
        return bar

    def _set_shape_type(self, shape_type: str):
        self.rect_button.setChecked(shape_type == "rect")
        self.polygon_button.setChecked(shape_type == "polygon")
        self.image_label.set_draw_shape_type(shape_type)
        hint = ("Drag to draw a rectangle." if shape_type == "rect" else
                "Click to place each polygon point. Double-click or Enter "
                "to finish, Esc to cancel.")
        self._update_status(f"  |  {hint}")

    def _build_class_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(210)
        self.class_panel_layout = QVBoxLayout(panel)
        self.class_panel_layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("Classes")
        header.setObjectName("header")
        self.class_panel_layout.addWidget(header)
        self.class_panel_layout.addWidget(self._hline())

        self.class_group = QButtonGroup(self)
        self.class_rows_container = QVBoxLayout()
        self.class_panel_layout.addLayout(self.class_rows_container)
        self._rebuild_class_buttons()

        # add-new-class row
        self.class_panel_layout.addWidget(self._hline())
        add_row = QHBoxLayout()
        self.new_class_input = QLineEdit()
        self.new_class_input.setPlaceholderText("New class name")
        self.new_class_input.returnPressed.connect(self._add_class)
        add_row.addWidget(self.new_class_input)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.clicked.connect(self._add_class)
        add_row.addWidget(add_btn)
        self.class_panel_layout.addLayout(add_row)

        self.class_panel_layout.addWidget(self._hline())
        header2 = QLabel("Shortcuts")
        header2.setObjectName("header")
        self.class_panel_layout.addWidget(header2)

        shortcuts_text = (
            "1-9   Select class\n"
            "A/D   Prev / Next image\n"
            "Rect: drag to draw\n"
            "Polygon: click points,\n"
            "  double-click/Enter to\n"
            "  finish, Esc to cancel\n"
            "Click  Select shape\n"
            "Del    Delete selected\n"
            "Ctrl+Z  Undo\n"
            "Ctrl+Y  Redo\n"
            "Ctrl+S  Save\n"
            "+ / -   Zoom in / out\n"
            "0       Fit to window"
        )
        muted = QLabel(shortcuts_text)
        muted.setObjectName("muted")
        self.class_panel_layout.addWidget(muted)
        self.class_panel_layout.addStretch()
        return panel

    def _rebuild_class_buttons(self):
        # clear existing rows
        while self.class_rows_container.count():
            item = self.class_rows_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        for button in self.class_group.buttons():
            self.class_group.removeButton(button)

        for i, cls in enumerate(CLASSES):
            row = QHBoxLayout()
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(
                f"background-color:{CLASS_COLORS[i]}; border:1px solid #3c3c3c;")
            label_text = f"{i + 1}. {cls}" if i < 9 else cls
            rb = QRadioButton(label_text)
            if i == self.current_class:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, idx=i: self._set_class(idx) if checked else None)
            self.class_group.addButton(rb, i)
            row.addWidget(swatch)
            row.addWidget(rb)
            row.addStretch()
            self.class_rows_container.addLayout(row)

    def _add_class(self):
        name = self.new_class_input.text()
        success, message = add_custom_class(name)
        if success:
            self.new_class_input.clear()
            self._rebuild_class_buttons()
            self._select_class_button(len(CLASSES) - 1)
        else:
            QMessageBox.warning(self, "Cannot add class", message)

    def _build_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        header = QLabel("Shapes in image")
        header.setObjectName("header")
        layout.addWidget(header)
        layout.addWidget(self._hline())

        self.box_list = QListWidget()
        self.box_list.itemSelectionChanged.connect(self._on_box_list_select)
        layout.addWidget(self.box_list, 1)

        header2 = QLabel("File list")
        header2.setObjectName("header")
        layout.addWidget(header2)
        layout.addWidget(self._hline())

        self.file_list = QListWidget()
        self.file_list.itemSelectionChanged.connect(self._on_file_list_select)
        layout.addWidget(self.file_list, 1)
        return panel

    def _build_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("panel")
        bar.setFixedHeight(34)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)

        self.status_label = QLabel("No folder opened")
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        return bar

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3c3c3c;")
        line.setFixedHeight(1)
        return line

    # -------------------------------------------------------- shortcuts
    def _build_shortcuts(self):
        QShortcut(QKeySequence("A"), self, activated=self.prev_image)
        QShortcut(QKeySequence("D"), self, activated=self.next_image)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected_box)
        QShortcut(QKeySequence("Backspace"), self, activated=self.delete_selected_box)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_current)
        QShortcut(QKeySequence("+"), self, activated=lambda: self.image_label.apply_zoom(1.15))
        QShortcut(QKeySequence("="), self, activated=lambda: self.image_label.apply_zoom(1.15))
        QShortcut(QKeySequence("-"), self, activated=lambda: self.image_label.apply_zoom(1 / 1.15))
        QShortcut(QKeySequence("0"), self, activated=lambda: self.image_label.fit_to_window())
        for i in range(1, 10):
            QShortcut(QKeySequence(str(i)), self,
                      activated=lambda idx=i - 1: self._select_class_button(idx))

    def _select_class_button(self, idx: int):
        button = self.class_group.button(idx)
        if button:
            button.setChecked(True)

    def _set_class(self, idx: int):
        self.current_class = idx
        self.image_label.set_current_class(idx)

    # ------------------------------------------------------------ folder
    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder with images")
        if not folder:
            return
        paths = []
        for ext in IMAGE_EXTENSIONS:
            paths.extend(glob.glob(os.path.join(folder, f"*{ext}")))
            paths.extend(glob.glob(os.path.join(folder, f"*{ext.upper()}")))
        paths = sorted(set(paths))
        if not paths:
            QMessageBox.warning(self, "No images", "No supported images found in this folder.")
            return

        self.folder = folder
        self.image_paths = paths
        self.states = {}
        self.current_index = -1

        self.file_list.clear()
        for p in self.image_paths:
            self.file_list.addItem(os.path.basename(p))

        self._load_index(0)
        self._update_progress()

    def labels_dir(self) -> str:
        return os.path.join(self.folder, "labels")

    # ---------------------------------------------------------- navigation
    def _load_index(self, index: int):
        if not (0 <= index < len(self.image_paths)):
            return
        if self.current_index != -1:
            self._save_state(self.current_index)

        self.current_index = index
        path = self.image_paths[index]

        self.image_label.load_image(path)
        img_w, img_h = self.image_label.image_w, self.image_label.image_h

        if path not in self.states:
            state = ImageState()
            state.shapes = load_labels(path, self.labels_dir(), img_w, img_h)
            self.states[path] = state

        self.image_label.set_state(self.states[path])

        self.file_list.blockSignals(True)
        self.file_list.setCurrentRow(index)
        self.file_list.blockSignals(False)

        self._refresh_box_list()
        self._update_status()
        self._update_progress()

    def next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self._load_index(self.current_index + 1)

    def prev_image(self):
        if self.current_index > 0:
            self._load_index(self.current_index - 1)

    def _on_file_list_select(self):
        row = self.file_list.currentRow()
        if row >= 0 and row != self.current_index:
            self._load_index(row)

    # -------------------------------------------------------------- edit
    def delete_selected_box(self):
        self.image_label.delete_selected()

    def undo(self):
        self.image_label.undo()

    def redo(self):
        self.image_label.redo()

    def _on_shapes_changed(self):
        self._refresh_box_list()
        self._update_status()
        self._update_progress()

    def _on_shape_awaiting_class(self, index: int):
        state = self._current_state()
        if not state or not (0 <= index < len(state.shapes)):
            return

        dialog = ClassPickerDialog(self, default_class_id=self.current_class)
        dialog.exec_()  # blocks; user picks a class or adds a new one (both call accept())

        state.shapes[index].class_id = dialog.selected_class_id
        state.dirty = True

        # a new class may have been added inside the dialog — refresh the
        # side panel's class list to match
        self._rebuild_class_buttons()
        self._refresh_box_list()
        self.image_label.update()
        self._update_status()

    def _on_selection_changed(self, index):
        self.box_list.blockSignals(True)
        if index is None:
            self.box_list.clearSelection()
        else:
            self.box_list.setCurrentRow(index)
        self.box_list.blockSignals(False)

    def _on_mouse_moved(self, img_x, img_y):
        self._update_status(f"  |  x={int(img_x)}, y={int(img_y)}")

    def _on_box_list_select(self):
        row = self.box_list.currentRow()
        if row >= 0:
            self.image_label.select_index(row)

    # ------------------------------------------------------------- save
    def _current_state(self):
        if not self.image_paths or self.current_index == -1:
            return None
        return self.states.get(self.image_paths[self.current_index])

    def _save_state(self, index: int):
        if not (0 <= index < len(self.image_paths)):
            return
        path = self.image_paths[index]
        state = self.states.get(path)
        if state is None or not state.dirty:
            return
        save_labels(path, self.labels_dir(), state.shapes,
                    self.image_label.image_w, self.image_label.image_h)
        save_json_labels(path, self.labels_dir(), state.shapes,
                          self.image_label.image_w, self.image_label.image_h,
                          username=self.username)
        state.dirty = False

    def save_current(self):
        if self.current_index == -1:
            return
        self._save_state(self.current_index)
        QMessageBox.information(self, "Saved", "Annotations saved (YOLO .txt + .json).")
        self._update_progress()

    # ------------------------------------------------------------ export
    def export_dataset(self):
        if not self.folder:
            QMessageBox.warning(self, "No folder", "Open a folder first.")
            return
        self._save_state(self.current_index)

        export_dir = QFileDialog.getExistingDirectory(self, "Select export destination")
        if not export_dir:
            return

        images_out = os.path.join(export_dir, "images")
        labels_out = os.path.join(export_dir, "labels")
        os.makedirs(images_out, exist_ok=True)
        os.makedirs(labels_out, exist_ok=True)

        count = 0
        for path in self.image_paths:
            lp = label_path_for(path, self.labels_dir())
            if not os.path.exists(lp):
                continue
            shutil.copy2(path, os.path.join(images_out, os.path.basename(path)))
            shutil.copy2(lp, os.path.join(labels_out, os.path.basename(lp)))

            jp = os.path.join(self.labels_dir(),
                               os.path.splitext(os.path.basename(path))[0] + ".json")
            if os.path.exists(jp):
                shutil.copy2(jp, os.path.join(labels_out, os.path.basename(jp)))

            count += 1

        with open(os.path.join(export_dir, "classes.txt"), "w") as f:
            f.write("\n".join(CLASSES) + "\n")

        with open(os.path.join(export_dir, "data.yaml"), "w") as f:
            f.write(f"path: {export_dir}\n")
            f.write("train: images\n")
            f.write("val: images\n")
            f.write(f"nc: {len(CLASSES)}\n")
            f.write(f"names: {CLASSES}\n")

        QMessageBox.information(self, "Export complete",
                                 f"Exported {count} labeled images to:\n{export_dir}")

    # ----------------------------------------------------------- UI sync
    def _refresh_box_list(self):
        self.box_list.blockSignals(True)
        self.box_list.clear()
        state = self._current_state()
        if state:
            for i, shape in enumerate(state.shapes):
                label = CLASSES[shape.class_id] if shape.class_id < len(CLASSES) else "?"
                icon = "▭" if shape.shape_type == "rect" else "⬠"
                self.box_list.addItem(f"{i + 1}. {icon} {label}")
            if self.image_label.selected_index is not None:
                self.box_list.setCurrentRow(self.image_label.selected_index)
        self.box_list.blockSignals(False)

    def _update_status(self, extra: str = ""):
        if not self.image_paths:
            self.status_label.setText("No folder opened")
            return
        path = self.image_paths[self.current_index]
        state = self._current_state()
        n_shapes = len(state.shapes) if state else 0
        dirty = " [unsaved]" if state and state.dirty else ""
        text = (f"[{self.current_index + 1}/{len(self.image_paths)}] "
                f"{os.path.basename(path)}  |  "
                f"{self.image_label.image_w}x{self.image_label.image_h}  |  "
                f"{n_shapes} shape(s)  |  zoom {int(self.image_label.zoom * 100)}%{dirty}{extra}")
        self.status_label.setText(text)

    def _update_progress(self):
        if not self.image_paths:
            self.progress_bar.setValue(0)
            self.progress_label.setText("")
            return
        labeled = 0
        for path in self.image_paths:
            lp = label_path_for(path, self.labels_dir())
            state = self.states.get(path)
            if (state and state.shapes) or os.path.exists(lp):
                labeled += 1
        pct = int((labeled / len(self.image_paths)) * 100)
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"{labeled}/{len(self.image_paths)} labeled")

    # ------------------------------------------------------------- close
    def closeEvent(self, event):
        if self.current_index != -1:
            self._save_state(self.current_index)
        event.accept()