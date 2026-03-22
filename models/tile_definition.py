from dataclasses import dataclass, field
from typing import List, Tuple
from PyQt5.QtGui import QColor


@dataclass
class TileDefinition:
    name: str        # STL filename without extension
    stl_path: str    # Absolute path to the .stl file
    grid_w: int      # Width in grid cells (derived from bounding box X / 25mm)
    grid_h: int      # Height in grid cells (derived from bounding box Y / 25mm)
    grid_z: float    # Height in grid cell units (dz_mm / 25); minimum 0.1
    color: QColor    # Assigned deterministically from name hash
    # Normalized [0,1] XYZ triangles for 3D rendering.
    # Each entry is [(x0,y0,z0), (x1,y1,z1), (x2,y2,z2)] with coords in [0,1].
    # nz=0 is tile floor level; nz=1 is the tallest point in the mesh.
    view_triangles: List[List[Tuple[float, float, float]]] = field(default_factory=list)

    @staticmethod
    def color_for_name(name: str) -> QColor:
        hue = abs(hash(name)) % 360
        color = QColor.fromHsv(hue, 180, 210)
        return color
