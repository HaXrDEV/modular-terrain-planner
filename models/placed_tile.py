import math
from dataclasses import dataclass
from typing import List, Tuple

from models.tile_definition import TileDefinition


@dataclass
class PlacedTile:
    # Use identity-based hashing so PlacedTile instances can live in sets/dicts
    __hash__ = object.__hash__
    definition: TileDefinition
    grid_x: float   # may be fractional for free-placed tiles
    grid_y: float   # may be fractional for free-placed tiles
    rotation: int        # 0, 90, 180, or 270 degrees
    z_offset: float = 0.0  # Z position in grid-cell units; set when stacking on another tile

    @property
    def effective_w(self) -> int:
        """Width in grid cells, accounting for rotation."""
        if self.rotation in (90, 270):
            return self.definition.grid_h
        return self.definition.grid_w

    @property
    def effective_h(self) -> int:
        """Height in grid cells, accounting for rotation."""
        if self.rotation in (90, 270):
            return self.definition.grid_w
        return self.definition.grid_h

    def occupies(self) -> List[Tuple[int, int]]:
        """Returns all (x, y) grid cells this tile covers."""
        x0 = math.floor(self.grid_x)
        y0 = math.floor(self.grid_y)
        cells = []
        for dy in range(self.effective_h):
            for dx in range(self.effective_w):
                cells.append((x0 + dx, y0 + dy))
        return cells

    def model_matrix(self) -> "QMatrix4x4":
        """Build the OpenGL model matrix: translate → scale → rotate around tile centre.

        Returns a QMatrix4x4 suitable for use as the model transform in all
        rendering and picking code paths.
        """
        from PySide6.QtGui import QMatrix4x4
        m = QMatrix4x4()
        m.translate(float(self.grid_x), float(self.grid_y), self.z_offset)
        m.scale(float(self.effective_w), float(self.effective_h),
                float(self.definition.grid_z))
        if self.rotation != 0:
            m.translate(0.5, 0.5, 0.0)
            m.rotate(float(self.rotation), 0.0, 0.0, 1.0)
            m.translate(-0.5, -0.5, 0.0)
        return m
