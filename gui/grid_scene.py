from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPen, QColor, QBrush
from PyQt5.QtWidgets import QGraphicsScene, QGraphicsRectItem

from gui.tile_item import TileItem, CELL_PX
from models.grid_model import GridModel
from models.placed_tile import PlacedTile

GRID_LINE_COLOR = QColor(200, 200, 200)
GHOST_COLOR = QColor(100, 180, 255, 100)
GHOST_INVALID_COLOR = QColor(255, 80, 80, 100)


class GridScene(QGraphicsScene):
    def __init__(self, grid_model: GridModel) -> None:
        super().__init__()
        self._model = grid_model
        self._ghost_item: QGraphicsRectItem | None = None

        total_w = grid_model.GRID_COLS * CELL_PX
        total_h = grid_model.GRID_ROWS * CELL_PX
        self.setSceneRect(0, 0, total_w, total_h)

        self._draw_grid_lines()

    # ------------------------------------------------------------------
    # Grid lines
    # ------------------------------------------------------------------
    def _draw_grid_lines(self) -> None:
        pen = QPen(GRID_LINE_COLOR, 1)
        cols = self._model.GRID_COLS
        rows = self._model.GRID_ROWS

        for col in range(cols + 1):
            x = col * CELL_PX
            item = self.addLine(x, 0, x, rows * CELL_PX, pen)
            item.setZValue(0)

        for row in range(rows + 1):
            y = row * CELL_PX
            item = self.addLine(0, y, cols * CELL_PX, y, pen)
            item.setZValue(0)

    # ------------------------------------------------------------------
    # Tile rendering
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Remove all TileItems and redraw from GridModel state."""
        for item in list(self.items()):
            if isinstance(item, TileItem):
                self.removeItem(item)
        for pt in self._model.all_placed():
            self.addItem(TileItem(pt, CELL_PX))

    # ------------------------------------------------------------------
    # Ghost preview
    # ------------------------------------------------------------------
    def show_ghost(self, placed_tile: PlacedTile, valid: bool) -> None:
        """Show a semi-transparent preview rectangle."""
        self.hide_ghost()
        x = placed_tile.grid_x * CELL_PX
        y = placed_tile.grid_y * CELL_PX
        w = placed_tile.effective_w * CELL_PX
        h = placed_tile.effective_h * CELL_PX

        color = GHOST_COLOR if valid else GHOST_INVALID_COLOR
        self._ghost_item = self.addRect(x, y, w, h, QPen(Qt.NoPen), QBrush(color))
        self._ghost_item.setZValue(2)

    def hide_ghost(self) -> None:
        if self._ghost_item is not None:
            self.removeItem(self._ghost_item)
            self._ghost_item = None

    # ------------------------------------------------------------------
    # Coordinate helper
    # ------------------------------------------------------------------
    def cell_from_scene_pos(self, pos: QPointF):
        """Convert scene coordinates to (grid_x, grid_y)."""
        gx = int(pos.x() // CELL_PX)
        gy = int(pos.y() // CELL_PX)
        return gx, gy
