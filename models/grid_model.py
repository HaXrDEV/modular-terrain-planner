from typing import Dict, List, Optional, Set

from models.placed_tile import PlacedTile


class GridModel:
    CELL_SIZE_MM: float = 12.5

    def __init__(self, cols: int = 80, rows: int = 80) -> None:
        self.GRID_COLS = cols
        self.GRID_ROWS = rows
        self._placed: List[PlacedTile] = []
        # Overlap index: (x, y, z_offset) → set of PlacedTile
        #   Used by can_place() for O(1) collision checks.
        self._cell_index: Dict[tuple, Set[PlacedTile]] = {}
        # XY index: (x, y) → set of PlacedTile
        #   Used by top_z_at() / topmost_at() for O(1) lookups by grid cell.
        self._xy_index: Dict[tuple, Set[PlacedTile]] = {}

    # ------------------------------------------------------------------
    # Index maintenance
    # ------------------------------------------------------------------

    def _index_add(self, tile: PlacedTile) -> None:
        for (x, y) in tile.occupies():
            key = (x, y, tile.z_offset)
            if key not in self._cell_index:
                self._cell_index[key] = set()
            self._cell_index[key].add(tile)

            xy = (x, y)
            if xy not in self._xy_index:
                self._xy_index[xy] = set()
            self._xy_index[xy].add(tile)

    def _index_remove(self, tile: PlacedTile) -> None:
        for (x, y) in tile.occupies():
            key = (x, y, tile.z_offset)
            bucket = self._cell_index.get(key)
            if bucket is not None:
                bucket.discard(tile)
                if not bucket:
                    del self._cell_index[key]

            xy = (x, y)
            bucket = self._xy_index.get(xy)
            if bucket is not None:
                bucket.discard(tile)
                if not bucket:
                    del self._xy_index[xy]

    def _index_rebuild(self) -> None:
        self._cell_index.clear()
        self._xy_index.clear()
        for pt in self._placed:
            self._index_add(pt)

    # ------------------------------------------------------------------
    # Placement / removal
    # ------------------------------------------------------------------

    def can_place(self, tile: PlacedTile) -> bool:
        """Check bounds and no overlap with existing placed tiles."""
        for (x, y) in tile.occupies():
            if x < 0 or y < 0 or x >= self.GRID_COLS or y >= self.GRID_ROWS:
                return False
            if (x, y, tile.z_offset) in self._cell_index:
                return False
        return True

    def place(self, tile: PlacedTile) -> bool:
        """Place tile if valid. Returns True on success."""
        if self.can_place(tile):
            self._placed.append(tile)
            self._index_add(tile)
            return True
        return False

    def force_place(self, tile: PlacedTile) -> None:
        """Place tile unconditionally (used for free/Ctrl placement)."""
        self._placed.append(tile)
        self._index_add(tile)

    def top_z_at(self, gx: int, gy: int) -> float:
        """Return the highest z_offset + grid_z among tiles covering (gx, gy), or 0.0."""
        tiles = self._xy_index.get((gx, gy))
        if not tiles:
            return 0.0
        return max(pt.z_offset + pt.definition.grid_z for pt in tiles)

    def topmost_at(self, gx: int, gy: int) -> Optional["PlacedTile"]:
        """Return the topmost PlacedTile (highest z_offset) covering (gx, gy), or None."""
        tiles = self._xy_index.get((gx, gy))
        if not tiles:
            return None
        return max(tiles, key=lambda pt: pt.z_offset)

    def remove_at(self, gx: int, gy: int) -> bool:
        """Remove the topmost tile (highest z_offset) covering (gx, gy). Returns True if removed."""
        target = self.topmost_at(gx, gy)
        if target is None:
            return False
        return self.remove_tile(target)

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
        self._placed = [pt for pt in self._placed if self._in_bounds(pt)]
        self._index_rebuild()
        return before - len(self._placed)

    def _in_bounds(self, tile: PlacedTile) -> bool:
        """Bounds-only check (ignores overlap)."""
        for (x, y) in tile.occupies():
            if x < 0 or y < 0 or x >= self.GRID_COLS or y >= self.GRID_ROWS:
                return False
        return True

    # Keep old name as alias for backwards compatibility with project loading
    can_place_silent = _in_bounds

    def remove_tile(self, tile: PlacedTile) -> bool:
        """Remove a specific PlacedTile by identity (not value equality)."""
        for i, pt in enumerate(self._placed):
            if pt is tile:
                self._placed.pop(i)
                self._index_remove(tile)
                return True
        return False

    def clear(self) -> None:
        self._placed.clear()
        self._cell_index.clear()
        self._xy_index.clear()
