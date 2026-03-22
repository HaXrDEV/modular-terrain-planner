from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import (
    QBrush, QColor, QPen, QFont, QPainter, QPolygonF, QPainterPath,
)
from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from PyQt5.QtWidgets import QGraphicsRectItem

from models.placed_tile import PlacedTile

CELL_PX = 32  # pixels per grid cell at 1× zoom


class TileItem(QGraphicsRectItem):
    def __init__(self, placed_tile: PlacedTile, cell_px: int = CELL_PX) -> None:
        x = placed_tile.grid_x * cell_px
        y = placed_tile.grid_y * cell_px
        w = placed_tile.effective_w * cell_px
        h = placed_tile.effective_h * cell_px
        super().__init__(x, y, w, h)

        self._placed = placed_tile
        self._cell_px = cell_px
        self._x = x
        self._y = y
        self._w = w
        self._h = h

        # Invisible border — we draw everything in paint()
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setZValue(1)

        # Label on top
        label = QGraphicsTextItem(placed_tile.definition.name, self)
        font = QFont("Arial", max(6, cell_px // 5), QFont.Bold)
        label.setFont(font)
        label.setDefaultTextColor(Qt.white)
        label_rect = label.boundingRect()
        label.setPos(
            x + (w - label_rect.width()) / 2,
            y + (h - label_rect.height()) / 2,
        )
        label.setZValue(3)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        defn = self._placed.definition
        x, y, w, h = self._x, self._y, self._w, self._h

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        triangles = defn.view_triangles
        if triangles:
            self._paint_mesh(painter, triangles, x, y, w, h, defn.color)
        else:
            # Fallback: plain colored rectangle
            fill = QColor(defn.color)
            fill.setAlpha(200)
            painter.fillRect(QRectF(x, y, w, h), fill)

        # Tile border
        border_color = QColor(defn.color).darker(160)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        painter.restore()

    def _paint_mesh(
        self,
        painter: QPainter,
        triangles,
        x: float, y: float, w: float, h: float,
        base_color: QColor,
    ) -> None:
        """Draw XY-projected STL triangles scaled into the tile's pixel rect."""
        rotation = self._placed.rotation

        # Determine effective width/height before rotation swap for correct scaling
        defn = self._placed.definition

        fill = QColor(base_color)
        fill.setAlpha(210)
        edge_color = QColor(base_color).darker(180)
        edge_color.setAlpha(120)

        fill_brush = QBrush(fill)
        edge_pen = QPen(edge_color, 0.4)

        painter.setPen(edge_pen)
        painter.setBrush(fill_brush)

        for tri in triangles:
            pts = []
            for (nx, ny) in tri:
                # Apply rotation around tile centre (in normalised 0-1 space)
                rx, ry = _rotate_norm(nx, ny, rotation)
                pts.append(QPointF(x + rx * w, y + ry * h))
            poly = QPolygonF(pts)
            painter.drawPolygon(poly)


def _rotate_norm(nx: float, ny: float, rotation: int):
    """Rotate a normalised (0-1) point around the centre (0.5, 0.5)."""
    cx, cy = nx - 0.5, ny - 0.5
    if rotation == 0:
        return nx, ny
    elif rotation == 90:
        return 0.5 - cy, 0.5 + cx
    elif rotation == 180:
        return 1.0 - nx, 1.0 - ny
    elif rotation == 270:
        return 0.5 + cy, 0.5 - cx
    return nx, ny
