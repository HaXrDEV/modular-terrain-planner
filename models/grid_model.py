from typing import Dict, List, Optional

from models.placed_tile import PlacedTile


class GridModel:
    GRID_COLS: int = 40
    GRID_ROWS: int = 40
    CELL_SIZE_MM: float = 25.0

    def __init__(self) -> None:
        self._placed: List[PlacedTile] = []

    def can_place(self, tile: PlacedTile) -> bool:
        """Check bounds and no overlap with existing placed tiles."""
        cells = tile.occupies()
        # Bounds check
        for (x, y) in cells:
            if x < 0 or y < 0 or x >= self.GRID_COLS or y >= self.GRID_ROWS:
                return False
        # Overlap check
        occupied = set()
        for pt in self._placed:
            for cell in pt.occupies():
                occupied.add(cell)
        for cell in cells:
            if cell in occupied:
                return False
        return True

    def place(self, tile: PlacedTile) -> bool:
        """Place tile if valid. Returns True on success."""
        if self.can_place(tile):
            self._placed.append(tile)
            return True
        return False

    def remove_at(self, gx: int, gy: int) -> bool:
        """Remove the first tile whose cells include (gx, gy). Returns True if removed."""
        for i, pt in enumerate(self._placed):
            if (gx, gy) in pt.occupies():
                self._placed.pop(i)
                return True
        return False

    def get_counts(self) -> Dict[str, int]:
        """Returns {tile_name: count} aggregated from all placed tiles."""
        counts: Dict[str, int] = {}
        for pt in self._placed:
            counts[pt.definition.name] = counts.get(pt.definition.name, 0) + 1
        return counts

    def all_placed(self) -> List[PlacedTile]:
        return list(self._placed)

    def clear(self) -> None:
        self._placed.clear()
