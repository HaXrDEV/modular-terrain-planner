from dataclasses import dataclass
from typing import List, Tuple

from models.tile_definition import TileDefinition


@dataclass
class PlacedTile:
    definition: TileDefinition
    grid_x: int
    grid_y: int
    rotation: int  # 0, 90, 180, or 270 degrees

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
        cells = []
        for dy in range(self.effective_h):
            for dx in range(self.effective_w):
                cells.append((self.grid_x + dx, self.grid_y + dy))
        return cells
