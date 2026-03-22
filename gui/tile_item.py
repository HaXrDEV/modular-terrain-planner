from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QBrush, QColor, QPen, QFont, QPainter
from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QStyleOptionGraphicsItem

from models.placed_tile import PlacedTile

CELL_PX = 32  # pixels per grid cell at 1× zoom


def _rotate_norm_3d(nx: float, ny: float, nz: float, rotation: int):
    """Z-axis rotation of normalised (nx, ny) around (0.5, 0.5); nz unchanged."""
    cx, cy = nx - 0.5, ny - 0.5
    if rotation == 0:   return nx, ny, nz
    if rotation == 90:  return 0.5 - cy, 0.5 + cx, nz
    if rotation == 180: return 1.0 - nx, 1.0 - ny, nz
    if rotation == 270: return 0.5 + cy, 0.5 - cx, nz
    return nx, ny, nz


def _rotate_norm(nx: float, ny: float, rotation: int):
    rx, ry, _ = _rotate_norm_3d(nx, ny, 0.0, rotation)
    return rx, ry


class TileItem(QGraphicsRectItem):
    def __init__(self, placed_tile: PlacedTile, cell_px: int = CELL_PX) -> None:
        x = placed_tile.grid_x * cell_px
        y = placed_tile.grid_y * cell_px
        w = placed_tile.effective_w * cell_px
        h = placed_tile.effective_h * cell_px
        super().__init__(x, y, w, h)

        self._placed = placed_tile
        self._x, self._y, self._w, self._h = x, y, w, h

        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setZValue(1)

        # Name label (child item, drawn automatically on top)
        label = QGraphicsTextItem(placed_tile.definition.name, self)
        font = QFont("Arial", max(6, cell_px // 5), QFont.Bold)
        label.setFont(font)
        label.setDefaultTextColor(Qt.white)
        lr = label.boundingRect()
        label.setPos(x + (w - lr.width()) / 2, y + (h - lr.height()) / 2)
        label.setZValue(3)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        from gui.tile_renderer import TileRenderer

        defn = self._placed.definition
        x, y, w, h = self._x, self._y, self._w, self._h

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Try OpenGL-rendered pixmap
        renderer = TileRenderer.instance()
        drawn = False
        if renderer is not None:
            pixmap = renderer.get_pixmap(defn, self._placed.rotation)
            if pixmap is not None and not pixmap.isNull():
                painter.drawPixmap(
                    QRectF(x, y, w, h),
                    pixmap,
                    QRectF(0, 0, pixmap.width(), pixmap.height()),
                )
                drawn = True

        # Fallback: solid color rectangle
        if not drawn:
            fill = QColor(defn.color)
            fill.setAlpha(200)
            painter.fillRect(QRectF(x, y, w, h), fill)

        # Grid-aligned border
        painter.setPen(QPen(QColor(defn.color).darker(160), 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))

        painter.restore()
