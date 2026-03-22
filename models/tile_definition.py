from dataclasses import dataclass, field
from PyQt5.QtGui import QColor

import numpy as np


@dataclass
class TileDefinition:
    name: str        # STL filename without extension
    stl_path: str    # Absolute path to the .stl file
    grid_w: int      # Width in grid cells (derived from bounding box X / 25mm)
    grid_h: int      # Height in grid cells (derived from bounding box Y / 25mm)
    grid_z: float    # Height in grid cell units (dz_mm / 25); minimum 0.1
    color: QColor    # Assigned deterministically from name hash
    # Normalised [0,1] XYZ triangle vertices for 3D rendering.
    # Shape: (N, 3, 3) — N triangles × 3 vertices × (x, y, z).
    # nz=0 is tile floor level; nz=1 is the tallest point in the mesh.
    # compare=False: numpy arrays can't be used in __eq__ comparisons.
    view_triangles: np.ndarray = field(
        default_factory=lambda: np.empty((0, 3, 3), dtype=np.float32),
        compare=False,
    )

    @staticmethod
    def color_for_name(name: str) -> QColor:
        hue = abs(hash(name)) % 360
        color = QColor.fromHsv(hue, 180, 210)
        return color
