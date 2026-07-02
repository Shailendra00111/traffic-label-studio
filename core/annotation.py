"""
core/annotation.py
===================
Data model for annotation shapes (rectangles AND polygons), per-image
annotation state (undo/redo history), YOLO import/export (rect -> standard
YOLO detection format, polygon -> YOLO-seg format), JSON export with
metadata, and user-editable class list (persisted to classes.json).
"""

import os
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLASSES_FILE = os.path.join(PROJECT_ROOT, "classes.json")

DEFAULT_CLASSES = ["Car", "Bike", "Bus", "Truck", "Auto", "Person"]
DEFAULT_COLORS = [
    "#e74c3c",  # red
    "#3498db",  # blue
    "#f1c40f",  # yellow
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#2ecc71",  # green
]
# extra colors cycled through when user adds custom classes beyond the palette
EXTRA_COLOR_POOL = [
    "#e67e22", "#ff6b81", "#00cec9", "#a29bfe", "#fdcb6e",
    "#55efc4", "#fab1a0", "#74b9ff", "#d63031", "#00b894",
]

CLASSES: List[str] = []
CLASS_COLORS: List[str] = []


def _color_for_index(index: int) -> str:
    if index < len(DEFAULT_COLORS):
        return DEFAULT_COLORS[index]
    pool_index = (index - len(DEFAULT_COLORS)) % len(EXTRA_COLOR_POOL)
    return EXTRA_COLOR_POOL[pool_index]


def load_classes():
    """Load classes (+ colors) from classes.json, creating it with the
    defaults on first run. Mutates CLASSES/CLASS_COLORS in place so other
    modules that did `from core.annotation import CLASSES` keep seeing
    updates."""
    CLASSES.clear()
    CLASS_COLORS.clear()

    if os.path.exists(CLASSES_FILE):
        try:
            with open(CLASSES_FILE, "r") as f:
                data = json.load(f)
            for entry in data:
                CLASSES.append(entry["name"])
                CLASS_COLORS.append(entry["color"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    if not CLASSES:
        for i, name in enumerate(DEFAULT_CLASSES):
            CLASSES.append(name)
            CLASS_COLORS.append(_color_for_index(i))
        _persist_classes()


def _persist_classes():
    data = [{"name": n, "color": c} for n, c in zip(CLASSES, CLASS_COLORS)]
    with open(CLASSES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_custom_class(name: str) -> Tuple[bool, str]:
    """Add a new class. Returns (success, message)."""
    name = name.strip()
    if not name:
        return False, "Class name cannot be empty."
    if name in CLASSES:
        return False, f'Class "{name}" already exists.'

    CLASSES.append(name)
    CLASS_COLORS.append(_color_for_index(len(CLASSES) - 1))
    _persist_classes()
    return True, f'Class "{name}" added.'


# Load classes as soon as this module is imported.
load_classes()


@dataclass
class Shape:
    """A single annotation: either a rectangle (2 points: opposite corners)
    or a polygon (3+ points, in order)."""
    shape_type: str  # "rect" or "polygon"
    points: List[Tuple[float, float]]
    class_id: int

    def copy(self) -> "Shape":
        return Shape(self.shape_type, list(self.points), self.class_id)

    def bounding_rect(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def to_yolo(self, img_w: int, img_h: int) -> str:
        if self.shape_type == "rect":
            (x1, y1), (x2, y2) = self.points[0], self.points[1]
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            cx = ((x1 + x2) / 2) / img_w
            cy = ((y1 + y2) / 2) / img_h
            w = (x2 - x1) / img_w
            h = (y2 - y1) / img_h
            return f"{self.class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"
        else:
            coords = []
            for (x, y) in self.points:
                coords.append(f"{x / img_w:.6f}")
                coords.append(f"{y / img_h:.6f}")
            return f"{self.class_id} " + " ".join(coords)

    @staticmethod
    def from_yolo(line: str, img_w: int, img_h: int) -> "Shape":
        parts = line.strip().split()
        class_id = int(parts[0])
        nums = [float(p) for p in parts[1:]]

        if len(nums) == 4:
            cx, cy, w, h = nums
            cx *= img_w
            cy *= img_h
            w *= img_w
            h *= img_h
            x1, y1 = cx - w / 2, cy - h / 2
            x2, y2 = cx + w / 2, cy + h / 2
            return Shape("rect", [(x1, y1), (x2, y2)], class_id)
        else:
            points = []
            for i in range(0, len(nums) - 1, 2):
                points.append((nums[i] * img_w, nums[i + 1] * img_h))
            return Shape("polygon", points, class_id)


@dataclass
class ImageState:
    """Annotation state + undo/redo history for a single image."""
    shapes: List[Shape] = field(default_factory=list)
    undo_stack: List[List[Shape]] = field(default_factory=list)
    redo_stack: List[List[Shape]] = field(default_factory=list)
    dirty: bool = False

    def snapshot(self):
        """Call BEFORE mutating self.shapes to enable undo."""
        self.undo_stack.append([s.copy() for s in self.shapes])
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append([s.copy() for s in self.shapes])
        self.shapes = self.undo_stack.pop()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append([s.copy() for s in self.shapes])
        self.shapes = self.redo_stack.pop()
        self.dirty = True
        return True


def label_path_for(image_path: str, labels_dir: str) -> str:
    name = os.path.splitext(os.path.basename(image_path))[0] + ".txt"
    return os.path.join(labels_dir, name)


def json_path_for(image_path: str, labels_dir: str) -> str:
    name = os.path.splitext(os.path.basename(image_path))[0] + ".json"
    return os.path.join(labels_dir, name)


def load_labels(image_path: str, labels_dir: str, img_w: int, img_h: int) -> List[Shape]:
    path = label_path_for(image_path, labels_dir)
    shapes: List[Shape] = []
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    shapes.append(Shape.from_yolo(line, img_w, img_h))
                except (ValueError, IndexError):
                    continue
    return shapes


def save_labels(image_path: str, labels_dir: str, shapes: List[Shape],
                 img_w: int, img_h: int):
    os.makedirs(labels_dir, exist_ok=True)
    path = label_path_for(image_path, labels_dir)
    with open(path, "w") as f:
        for shape in shapes:
            f.write(shape.to_yolo(img_w, img_h) + "\n")


def save_json_labels(image_path: str, labels_dir: str, shapes: List[Shape],
                      img_w: int, img_h: int, username: str = ""):
    """Save annotations as JSON with class names, shape type, the logged-in
    user, and a timestamp — in addition to the YOLO .txt format."""
    os.makedirs(labels_dir, exist_ok=True)
    path = json_path_for(image_path, labels_dir)

    shape_entries = []
    for shape in shapes:
        class_name = CLASSES[shape.class_id] if 0 <= shape.class_id < len(CLASSES) else "Unknown"
        entry = {
            "class": class_name,
            "shape_type": shape.shape_type,
            "points": [[round(x, 2), round(y, 2)] for (x, y) in shape.points],
        }
        if shape.shape_type == "rect":
            x1, y1, x2, y2 = shape.bounding_rect()
            entry["x1"], entry["y1"], entry["x2"], entry["y2"] = (
                round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2))
        shape_entries.append(entry)

    data = {
        "image": os.path.basename(image_path),
        "labeled_by": username or "unknown",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "image_width": img_w,
        "image_height": img_h,
        "shapes": shape_entries,
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)