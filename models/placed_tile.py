import math
from dataclasses import dataclass
from typing import List, Tuple

from models.tile_definition import TileDefinition


@dataclass
class PlacedTile:
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
