from PyQt5.QtCore import Qt, pyqtSignal, QPointF
from PyQt5.QtGui import QWheelEvent, QMouseEvent, QKeyEvent, QPainter
from PyQt5.QtWidgets import QGraphicsView

from gui.grid_scene import GridScene


class GridView(QGraphicsView):
    # Emitted with (grid_x, grid_y)
    tile_place_requested = pyqtSignal(int, int)
    tile_remove_requested = pyqtSignal(int, int)
    rotate_requested = pyqtSignal()
    hover_cell_changed = pyqtSignal(int, int)

    _MIN_ZOOM = 0.25
    _MAX_ZOOM = 4.0

    def __init__(self, scene: GridScene) -> None:
        super().__init__(scene)
        self._scene = scene
        self._zoom = 1.0
        self._last_hover: tuple[int, int] = (-1, -1)

        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            new_zoom = self._zoom * factor
            new_zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, new_zoom))
            factor = new_zoom / self._zoom
            self._zoom = new_zoom
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    # ------------------------------------------------------------------
    # Pan with middle mouse
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            # Simulate left-press so QGraphicsView starts panning
            from PyQt5.QtCore import QEvent
            from PyQt5.QtGui import QMouseEvent as QME
            fake = QME(
                QEvent.MouseButtonPress,
                event.pos(),
                Qt.LeftButton,
                Qt.LeftButton,
                event.modifiers(),
            )
            super().mousePressEvent(fake)
        elif event.button() == Qt.LeftButton:
            gx, gy = self._grid_pos(event)
            self.tile_place_requested.emit(gx, gy)
        elif event.button() == Qt.RightButton:
            gx, gy = self._grid_pos(event)
            self.tile_remove_requested.emit(gx, gy)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        gx, gy = self._grid_pos(event)
        if (gx, gy) != self._last_hover:
            self._last_hover = (gx, gy)
            self.hover_cell_changed.emit(gx, gy)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_R:
            self.rotate_requested.emit()
        elif event.key() == Qt.Key_Delete:
            gx, gy = self._last_hover
            self.tile_remove_requested.emit(gx, gy)
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    def _grid_pos(self, event: QMouseEvent) -> tuple[int, int]:
        scene_pos: QPointF = self.mapToScene(event.pos())
        return self._scene.cell_from_scene_pos(scene_pos)
