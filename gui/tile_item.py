from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QBrush, QColor, QPen, QFont
from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

from models.placed_tile import PlacedTile

CELL_PX = 32  # pixels per grid cell at 1× zoom


class TileItem(QGraphicsRectItem):
    def __init__(self, placed_tile: PlacedTile, cell_px: int = CELL_PX) -> None:
        x = placed_tile.grid_x * cell_px
        y = placed_tile.grid_y * cell_px
        w = placed_tile.effective_w * cell_px
        h = placed_tile.effective_h * cell_px
        super().__init__(x, y, w, h)

        self.placed_tile = placed_tile

        # Fill with tile color at 70% opacity
        fill = QColor(placed_tile.definition.color)
        fill.setAlpha(178)  # ~70% of 255
        self.setBrush(QBrush(fill))
        self.setPen(QPen(Qt.black, 1))
        self.setZValue(1)

        # Label
        label = QGraphicsTextItem(placed_tile.definition.name, self)
        font = QFont("Arial", max(6, cell_px // 5))
        label.setFont(font)
        label.setDefaultTextColor(Qt.black)

        # Center the label inside the rect
        label_rect = label.boundingRect()
        label.setPos(
            x + (w - label_rect.width()) / 2,
            y + (h - label_rect.height()) / 2,
        )
