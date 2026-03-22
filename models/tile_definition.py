from dataclasses import dataclass
from PyQt5.QtGui import QColor


@dataclass
class TileDefinition:
    name: str        # STL filename without extension
    stl_path: str    # Absolute path to the .stl file
    grid_w: int      # Width in grid cells (derived from bounding box X / 25mm)
    grid_h: int      # Height in grid cells (derived from bounding box Y / 25mm)
    color: QColor    # Assigned deterministically from name hash

    @staticmethod
    def color_for_name(name: str) -> QColor:
        hue = abs(hash(name)) % 360
        color = QColor.fromHsv(hue, 180, 210)
        return color
