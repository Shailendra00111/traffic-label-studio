"""
core/image_canvas.py
=====================
ImageCanvas: a QLabel subclass that displays the current image and handles
all mouse interaction for drawing, moving, and resizing annotation shapes —
both rectangles (drag corner-to-corner) and polygons (click point-by-point,
double-click / Enter to close, Esc to cancel).
"""

from typing import Optional, Tuple, List

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QCursor, QPolygonF
from PyQt5.QtWidgets import QLabel

from core.annotation import Shape, ImageState, CLASSES, CLASS_COLORS

ZOOM_MIN = 0.2
ZOOM_MAX = 5.0
ZOOM_STEP = 1.15
HANDLE_SIZE = 8
SNAP_RADIUS = 12  # widget pixels — click within this of the start point to close a polygon


def _point_in_polygon(px: float, py: float, points: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(points)
    inside = False
    x1, y1 = points[0]
    for i in range(1, n + 1):
        x2, y2 = points[i % n]
        if py > min(y1, y2):
            if py <= max(y1, y2):
                if px <= max(x1, x2):
                    if y1 != y2:
                        x_intersect = (py - y1) * (x2 - x1) / (y2 - y1) + x1
                    else:
                        x_intersect = px
                    if x1 == x2 or px <= x_intersect:
                        inside = not inside
        x1, y1 = x2, y2
    return inside


class ImageCanvas(QLabel):
    """Displays an image and lets the user draw/edit rectangle or polygon shapes."""

    shapesChanged = pyqtSignal()
    selectionChanged = pyqtSignal(object)  # emits selected index or None
    mouseMovedOnImage = pyqtSignal(float, float)
    shapeAwaitingClass = pyqtSignal(int)  # emitted right after a shape is finished

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setStyleSheet("background-color: #111111;")
        self.setCursor(QCursor(Qt.CrossCursor))
        self.setFocusPolicy(Qt.StrongFocus)

        self.pixmap_orig: Optional[QPixmap] = None
        self.image_w = 0
        self.image_h = 0

        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self.state: Optional[ImageState] = None
        self.current_class = 0
        self.selected_index: Optional[int] = None

        self.draw_shape_type = "rect"  # "rect" or "polygon"

        # rect drawing / editing
        self.drag_mode: Optional[str] = None  # "new_rect"|"move"|"resize"|"polygon_draw"
        self.drag_handle: Optional[str] = None
        self.draw_start: Optional[Tuple[float, float]] = None
        self.drag_last: Optional[Tuple[int, int]] = None
        self.temp_rect: Optional[Tuple[int, int, int, int]] = None

        # polygon-in-progress
        self.polygon_points: List[Tuple[float, float]] = []
        self.polygon_cursor: Optional[Tuple[int, int]] = None

    # ------------------------------------------------------------- setup
    def load_image(self, path: str):
        self.pixmap_orig = QPixmap(path)
        self.image_w = self.pixmap_orig.width()
        self.image_h = self.pixmap_orig.height()
        self.fit_to_window()

    def set_state(self, state: ImageState):
        self.state = state
        self.selected_index = None
        self._cancel_polygon()
        self.selectionChanged.emit(None)
        self.update()

    def set_current_class(self, class_id: int):
        self.current_class = class_id

    def set_draw_shape_type(self, shape_type: str):
        self._cancel_polygon()
        self.draw_shape_type = shape_type
        self.update()

    # --------------------------------------------------------- zoom/pan
    def fit_to_window(self):
        if not self.pixmap_orig or self.image_w == 0 or self.image_h == 0:
            return
        cw, ch = max(self.width(), 10), max(self.height(), 10)
        scale = min(cw / self.image_w, ch / self.image_h)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, scale))
        self.offset_x = int((cw - self.image_w * self.zoom) / 2)
        self.offset_y = int((ch - self.image_h * self.zoom) / 2)
        self.update()

    def apply_zoom(self, factor: float):
        if not self.pixmap_orig:
            return
        old_zoom = self.zoom
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))
        cx, cy = self.width() / 2, self.height() / 2
        img_x = (cx - self.offset_x) / old_zoom
        img_y = (cy - self.offset_y) / old_zoom
        self.offset_x = int(cx - img_x * self.zoom)
        self.offset_y = int(cy - img_y * self.zoom)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap_orig:
            self.fit_to_window()

    # ---------------------------------------------------------- coords
    def img_to_widget(self, x: float, y: float) -> Tuple[float, float]:
        return x * self.zoom + self.offset_x, y * self.zoom + self.offset_y

    def widget_to_img(self, x: float, y: float) -> Tuple[float, float]:
        return (x - self.offset_x) / self.zoom, (y - self.offset_y) / self.zoom

    def clamp(self, x: float, y: float) -> Tuple[float, float]:
        return min(max(x, 0), self.image_w), min(max(y, 0), self.image_h)

    # ----------------------------------------------------------- paint
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111111"))

        if self.pixmap_orig:
            disp_w = max(1, int(self.image_w * self.zoom))
            disp_h = max(1, int(self.image_h * self.zoom))
            scaled = self.pixmap_orig.scaled(
                disp_w, disp_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(self.offset_x, self.offset_y, scaled)

        if self.state:
            for i, shape in enumerate(self.state.shapes):
                self._paint_shape(painter, i, shape)

        if self.drag_mode == "new_rect" and self.temp_rect:
            x1, y1, x2, y2 = self.temp_rect
            pen = QPen(QColor("#ffffff"))
            pen.setStyle(Qt.DashLine)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1).normalized())

        if self.polygon_points:
            self._paint_polygon_in_progress(painter)

        painter.end()

    def _paint_polygon_in_progress(self, painter: QPainter):
        pen = QPen(QColor("#ffffff"))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)

        widget_pts = [self.img_to_widget(x, y) for (x, y) in self.polygon_points]
        for i in range(len(widget_pts) - 1):
            painter.drawLine(QPointF(*widget_pts[i]), QPointF(*widget_pts[i + 1]))

        if self.polygon_cursor:
            painter.drawLine(QPointF(*widget_pts[-1]),
                              QPointF(self.polygon_cursor[0], self.polygon_cursor[1]))

        painter.setPen(QPen(QColor("#ffffff")))
        painter.setBrush(QColor("#ffffff"))
        for wx, wy in widget_pts:
            painter.drawEllipse(QPointF(wx, wy), 3, 3)

        # Highlight the starting point so the user knows where to click to
        # close the shape. It turns green + grows when the cursor is close
        # enough to snap-close.
        if widget_pts:
            start_wx, start_wy = widget_pts[0]
            near_close = False
            if self.polygon_cursor and len(self.polygon_points) >= 3:
                dist = ((self.polygon_cursor[0] - start_wx) ** 2 +
                        (self.polygon_cursor[1] - start_wy) ** 2) ** 0.5
                near_close = dist <= SNAP_RADIUS

            ring_color = QColor("#2ecc71") if near_close else QColor("#0e639c")
            radius = 9 if near_close else 6
            painter.setPen(QPen(ring_color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(start_wx, start_wy), radius, radius)

    def _paint_shape(self, painter: QPainter, index: int, shape: Shape):
        color = QColor(CLASS_COLORS[shape.class_id % len(CLASS_COLORS)])
        is_selected = (index == self.selected_index)
        pen = QPen(color)
        pen.setWidth(3 if is_selected else 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if shape.shape_type == "rect":
            (x1, y1), (x2, y2) = shape.points[0], shape.points[1]
            wx1, wy1 = self.img_to_widget(x1, y1)
            wx2, wy2 = self.img_to_widget(x2, y2)
            painter.drawRect(QRectF(wx1, wy1, wx2 - wx1, wy2 - wy1))
            label_x, label_y = min(wx1, wx2), min(wy1, wy2)
        else:
            widget_pts = [QPointF(*self.img_to_widget(x, y)) for (x, y) in shape.points]
            painter.drawPolygon(QPolygonF(widget_pts))
            xs = [p.x() for p in widget_pts]
            ys = [p.y() for p in widget_pts]
            label_x, label_y = min(xs), min(ys)

        label = CLASSES[shape.class_id] if shape.class_id < len(CLASSES) else "?"
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        text_w = 10 + 7 * len(label)
        painter.fillRect(QRectF(label_x, label_y - 18, text_w, 18), color)
        painter.setPen(QPen(QColor("#111111")))
        painter.drawText(QRectF(label_x + 4, label_y - 18, text_w, 18),
                          Qt.AlignVCenter | Qt.AlignLeft, label)

        if is_selected:
            painter.setPen(QPen(color))
            painter.setBrush(QColor("#ffffff"))
            for hx, hy in self._handle_positions(shape):
                painter.drawRect(QRectF(hx - 4, hy - 4, 8, 8))

    def _handle_positions(self, shape: Shape) -> List[Tuple[float, float]]:
        if shape.shape_type == "rect":
            (x1, y1), (x2, y2) = shape.points[0], shape.points[1]
            return [self.img_to_widget(x1, y1), self.img_to_widget(x2, y1),
                    self.img_to_widget(x1, y2), self.img_to_widget(x2, y2)]
        else:
            return [self.img_to_widget(x, y) for (x, y) in shape.points]

    # ------------------------------------------------------------ hits
    def _hit_test_handle(self, shape: Shape, wx: float, wy: float) -> Optional[str]:
        if shape.shape_type == "rect":
            (x1, y1), (x2, y2) = shape.points[0], shape.points[1]
            px1, py1 = self.img_to_widget(x1, y1)
            px2, py2 = self.img_to_widget(x2, y2)
            handles = {"tl": (px1, py1), "tr": (px2, py1),
                       "bl": (px1, py2), "br": (px2, py2)}
            for name, (hx, hy) in handles.items():
                if abs(wx - hx) <= HANDLE_SIZE and abs(wy - hy) <= HANDLE_SIZE:
                    return name
        else:
            for i, (x, y) in enumerate(shape.points):
                hx, hy = self.img_to_widget(x, y)
                if abs(wx - hx) <= HANDLE_SIZE and abs(wy - hy) <= HANDLE_SIZE:
                    return f"v{i}"
        return None

    def _hit_test_shape(self, img_x: float, img_y: float) -> Optional[int]:
        if not self.state:
            return None
        for i in reversed(range(len(self.state.shapes))):
            shape = self.state.shapes[i]
            if shape.shape_type == "rect":
                (x1, y1), (x2, y2) = shape.points[0], shape.points[1]
                x1, x2 = sorted((x1, x2))
                y1, y2 = sorted((y1, y2))
                if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                    return i
            else:
                if _point_in_polygon(img_x, img_y, shape.points):
                    return i
        return None

    # ----------------------------------------------------------- mouse
    def mousePressEvent(self, event):
        self.setFocus()
        if not self.pixmap_orig or event.button() != Qt.LeftButton or not self.state:
            return
        wx, wy = event.x(), event.y()

        # continuing to place polygon points
        if self.drag_mode == "polygon_draw":
            img_x, img_y = self.widget_to_img(wx, wy)
            img_x, img_y = self.clamp(img_x, img_y)

            # snap-close: clicking near the starting point finishes the polygon
            if len(self.polygon_points) >= 3:
                start_wx, start_wy = self.img_to_widget(*self.polygon_points[0])
                dist = ((wx - start_wx) ** 2 + (wy - start_wy) ** 2) ** 0.5
                if dist <= SNAP_RADIUS:
                    self._finish_polygon()
                    return

            self.polygon_points.append((img_x, img_y))
            self.update()
            return

        # resize handle on selected shape
        if self.selected_index is not None and 0 <= self.selected_index < len(self.state.shapes):
            handle = self._hit_test_handle(self.state.shapes[self.selected_index], wx, wy)
            if handle:
                self.drag_mode = "resize"
                self.drag_handle = handle
                self.state.snapshot()
                return

        img_x, img_y = self.widget_to_img(wx, wy)
        hit = self._hit_test_shape(img_x, img_y)

        if hit is not None:
            self.selected_index = hit
            self.selectionChanged.emit(hit)
            self.drag_mode = "move"
            self.drag_last = (wx, wy)
            self.state.snapshot()
            self.update()
        else:
            self.selected_index = None
            self.selectionChanged.emit(None)

            if self.draw_shape_type == "rect":
                self.drag_mode = "new_rect"
                cx, cy = self.clamp(img_x, img_y)
                self.draw_start = (cx, cy)
            else:
                cx, cy = self.clamp(img_x, img_y)
                self.polygon_points = [(cx, cy)]
                self.drag_mode = "polygon_draw"
            self.update()

    def mouseDoubleClickEvent(self, event):
        if self.drag_mode == "polygon_draw":
            self._finish_polygon()

    def mouseMoveEvent(self, event):
        wx, wy = event.x(), event.y()
        if self.pixmap_orig:
            img_x, img_y = self.widget_to_img(wx, wy)
            if 0 <= img_x <= self.image_w and 0 <= img_y <= self.image_h:
                self.mouseMovedOnImage.emit(img_x, img_y)

        if not self.state:
            return

        if self.drag_mode == "polygon_draw":
            self.polygon_cursor = (wx, wy)
            self.update()
        elif self.drag_mode == "new_rect" and self.draw_start:
            sx, sy = self.img_to_widget(*self.draw_start)
            self.temp_rect = (int(sx), int(sy), wx, wy)
            self.update()
        elif self.drag_mode == "move" and self.selected_index is not None:
            dx = (wx - self.drag_last[0]) / self.zoom
            dy = (wy - self.drag_last[1]) / self.zoom
            shape = self.state.shapes[self.selected_index]
            shape.points = [(px + dx, py + dy) for (px, py) in shape.points]
            self.drag_last = (wx, wy)
            self.update()
        elif self.drag_mode == "resize" and self.selected_index is not None:
            img_x, img_y = self.widget_to_img(wx, wy)
            img_x, img_y = self.clamp(img_x, img_y)
            shape = self.state.shapes[self.selected_index]
            if shape.shape_type == "rect":
                if self.drag_handle == "tl":
                    shape.points[0] = (img_x, img_y)
                elif self.drag_handle == "tr":
                    shape.points[1] = (img_x, shape.points[1][1])
                    shape.points[0] = (shape.points[0][0], img_y)
                elif self.drag_handle == "bl":
                    shape.points[0] = (img_x, shape.points[0][1])
                    shape.points[1] = (shape.points[1][0], img_y)
                elif self.drag_handle == "br":
                    shape.points[1] = (img_x, img_y)
            else:
                idx = int(self.drag_handle[1:])
                shape.points[idx] = (img_x, img_y)
            self.update()

    def mouseReleaseEvent(self, event):
        if not self.state:
            return

        if self.drag_mode == "new_rect" and self.draw_start:
            img_x, img_y = self.widget_to_img(event.x(), event.y())
            img_x, img_y = self.clamp(img_x, img_y)
            x1, y1 = self.draw_start
            x2, y2 = img_x, img_y
            if abs(x2 - x1) > 4 and abs(y2 - y1) > 4:
                self.state.snapshot()
                shape = Shape("rect", [(x1, y1), (x2, y2)], self.current_class)
                self.state.shapes.append(shape)
                self.state.dirty = True
                self.selected_index = len(self.state.shapes) - 1
                self.selectionChanged.emit(self.selected_index)
                self.shapesChanged.emit()
            self.drag_mode = None
            self.draw_start = None
            self.temp_rect = None

        elif self.drag_mode in ("move", "resize"):
            self.state.dirty = True
            self.shapesChanged.emit()
            self.drag_mode = None
            self.drag_handle = None
            self.drag_last = None

        # note: "polygon_draw" mode is intentionally NOT cleared here —
        # it continues across multiple clicks until finished/cancelled.
        self.update()

    def wheelEvent(self, event):
        factor = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        self.apply_zoom(factor)

    def keyPressEvent(self, event):
        if self.drag_mode == "polygon_draw":
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._finish_polygon()
                return
            if event.key() == Qt.Key_Escape:
                self._cancel_polygon()
                return
        super().keyPressEvent(event)

    # ------------------------------------------------------- polygon fsm
    def _finish_polygon(self):
        if len(self.polygon_points) >= 3 and self.state:
            self.state.snapshot()
            shape = Shape("polygon", list(self.polygon_points), self.current_class)
            self.state.shapes.append(shape)
            self.state.dirty = True
            new_index = len(self.state.shapes) - 1
            self.selected_index = new_index
            self.selectionChanged.emit(new_index)
            self.shapesChanged.emit()
            self.shapeAwaitingClass.emit(new_index)
        self._cancel_polygon()

    def _cancel_polygon(self):
        self.polygon_points = []
        self.polygon_cursor = None
        if self.drag_mode == "polygon_draw":
            self.drag_mode = None
        self.update()

    # ------------------------------------------------------------- api
    def select_index(self, index: Optional[int]):
        self.selected_index = index
        self.update()

    def delete_selected(self):
        if not self.state or self.selected_index is None:
            return
        self.state.snapshot()
        del self.state.shapes[self.selected_index]
        self.state.dirty = True
        self.selected_index = None
        self.selectionChanged.emit(None)
        self.shapesChanged.emit()
        self.update()

    def undo(self):
        if self.state and self.state.undo():
            self.selected_index = None
            self.selectionChanged.emit(None)
            self.shapesChanged.emit()
            self.update()

    def redo(self):
        if self.state and self.state.redo():
            self.selected_index = None
            self.selectionChanged.emit(None)
            self.shapesChanged.emit()
            self.update()