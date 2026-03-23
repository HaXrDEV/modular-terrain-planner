from typing import Dict, List, Optional

from models.placed_tile import PlacedTile


class GridModel:
    CELL_SIZE_MM: float = 12.5

    def __init__(self, cols: int = 80, rows: int = 80) -> None:
        self.GRID_COLS = cols
        self.GRID_ROWS = rows
        self._placed: List[PlacedTile] = []

    def can_place(self, tile: PlacedTile) -> bool:
        """Check bounds and no overlap with existing placed tiles."""
        cells = tile.occupies()
        # Bounds check
        for (x, y) in cells:
            if x < 0 or y < 0 or x >= self.GRID_COLS or y >= self.GRID_ROWS:
                return False
        # Overlap check — tiles at different z_offsets may share XY cells
        occupied = set()
        for pt in self._placed:
            for cell in pt.occupies():
                occupied.add((cell[0], cell[1], pt.z_offset))
        for cell in cells:
            if (cell[0], cell[1], tile.z_offset) in occupied:
                return False
        return True

    def place(self, tile: PlacedTile) -> bool:
        """Place tile if valid. Returns True on success."""
        if self.can_place(tile):
            self._placed.append(tile)
            return True
        return False

    def force_place(self, tile: PlacedTile) -> None:
        """Place tile unconditionally (used for free/Ctrl placement)."""
        self._placed.append(tile)

    def top_z_at(self, gx: int, gy: int) -> float:
        """Return the highest z_offset + grid_z among tiles covering (gx, gy), or 0.0."""
        best = 0.0
        for pt in self._placed:
            if (gx, gy) in pt.occupies():
                best = max(best, pt.z_offset + pt.definition.grid_z)
        return best

    def remove_at(self, gx: int, gy: int) -> bool:
        """Remove the topmost tile (highest z_offset) covering (gx, gy). Returns True if removed."""
        candidates = [(i, pt) for i, pt in enumerate(self._placed)
                      if (gx, gy) in pt.occupies()]
        if not candidates:
            return False
        idx, _ = max(candidates, key=lambda t: t[1].z_offset)
        self._placed.pop(idx)
        return True

    def get_counts(self) -> Dict[str, int]:
        """Returns {tile_name: count} aggregated from all placed tiles."""
        counts: Dict[str, int] = {}
        for pt in self._placed:
            counts[pt.definition.name] = counts.get(pt.definition.name, 0) + 1
        return counts

    def all_placed(self) -> List[PlacedTile]:
        return list(self._placed)

    def resize(self, cols: int, rows: int) -> int:
        """Change grid dimensions. Returns the number of tiles removed for being out of bounds."""
        self.GRID_COLS = cols
        self.GRID_ROWS = rows
        before = len(self._placed)
        self._placed = [pt for pt in self._placed if self.can_place_silent(pt)]
        return before - len(self._placed)

    def can_place_silent(self, tile: PlacedTile) -> bool:
        """Bounds-only check (ignores overlap). Used after resize to keep in-bounds tiles."""
        for (x, y) in tile.occupies():
            if x < 0 or y < 0 or x >= self.GRID_COLS or y >= self.GRID_ROWS:
                return False
        return True

    def clear(self) -> None:
        self._placed.clear()
