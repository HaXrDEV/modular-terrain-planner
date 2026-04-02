"""Orbit camera controller for the 3D grid view.

Owns all camera state (azimuth / elevation / distance / target / mode) and
provides mutation methods that emit `changed` so the owning widget can schedule
a repaint. No OpenGL or widget code lives here.
"""

import math
from typing import List

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QMatrix4x4, QVector3D


class CameraController(QObject):
    """Spherical-coordinate orbit camera.

    Signals
    -------
    changed
        Emitted whenever any camera state mutates. Connect to the owning
        widget's update() slot to schedule repaints.
    """

    changed = Signal()

    # Defaults
    DEFAULT_AZ   = 45.0
    DEFAULT_EL   = 55.0
    DEFAULT_DIST = 56.0

    def __init__(self, cx: float, cy: float, parent=None) -> None:
        super().__init__(parent)
        self._target:    List[float] = [cx, cy, 0.0]
        self._azimuth:   float = self.DEFAULT_AZ
        self._elevation: float = self.DEFAULT_EL
        self._distance:  float = self.DEFAULT_DIST
        self._ortho_mode: bool = False
        self._ortho_proj: bool = False   # debug: ortho projection with orbit camera

        # WASD smooth pan
        self._pan_speed: float = 0.008   # cells per tick per unit of distance
        self._pan_keys: set = set()
        self._pan_timer = QTimer(self)
        self._pan_timer.setInterval(16)  # ~60 fps
        self._pan_timer.timeout.connect(self._on_pan_tick)

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def target(self) -> List[float]:
        return self._target

    @property
    def azimuth(self) -> float:
        return self._azimuth

    @property
    def elevation(self) -> float:
        return self._elevation

    @property
    def distance(self) -> float:
        return self._distance

    @property
    def ortho_mode(self) -> bool:
        return self._ortho_mode

    # ------------------------------------------------------------------
    # Matrix computation
    # ------------------------------------------------------------------

    def eye_pos(self) -> QVector3D:
        """Convert spherical coordinates to world-space eye position."""
        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)
        dx = self._distance * math.cos(el) * math.cos(az)
        dy = self._distance * math.cos(el) * math.sin(az)
        dz = self._distance * math.sin(el)
        return QVector3D(
            self._target[0] + dx,
            self._target[1] + dy,
            self._target[2] + dz,
        )

    def get_proj_view(self, viewport_w: int, viewport_h: int):
        """Return (proj, view) QMatrix4x4 pair for the current camera state."""
        w = max(viewport_w, 1)
        h = max(viewport_h, 1)
        proj = QMatrix4x4()
        view = QMatrix4x4()

        if self._ortho_mode:
            # _distance doubles as the ortho half-height so scroll zoom works unchanged.
            half_h = max(self._distance, 0.1)
            half_w = half_h * (w / h)
            proj.ortho(-half_w, half_w, -half_h, half_h, -500.0, 500.0)
            tx, ty, tz = self._target
            view.lookAt(
                QVector3D(tx, ty, tz + 100.0),
                QVector3D(tx, ty, tz),
                QVector3D(0.0, 1.0, 0.0),   # world Y points up on screen
            )
        else:
            eye = self.eye_pos()
            view.lookAt(eye, QVector3D(*self._target), QVector3D(0.0, 0.0, 1.0))

            if self._ortho_proj:
                # Orthographic projection matched to the 45° FOV frustum at _distance.
                half_h = self._distance * math.tan(math.radians(22.5))
                half_w = half_h * (w / h)
                proj.ortho(-half_w, half_w, -half_h, half_h, -500.0, 500.0)
            else:
                proj.perspective(45.0, w / h, 0.05, 500.0)

        return proj, view

    # ------------------------------------------------------------------
    # Mutations — each emits changed()
    # ------------------------------------------------------------------

    def reset(self, cx: float, cy: float) -> None:
        """Reset to default view centred on (cx, cy)."""
        self._target    = [cx, cy, 0.0]
        self._azimuth   = self.DEFAULT_AZ
        self._elevation = self.DEFAULT_EL
        self._distance  = self.DEFAULT_DIST
        self.changed.emit()

    def zoom_to_bounds(self, min_x: float, min_y: float,
                       max_x: float, max_y: float) -> None:
        """Frame the camera to show the given world-space bounding box."""
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        span = max(max_x - min_x, max_y - min_y, 1.0)
        self._target = [cx, cy, 0.0]
        if self._ortho_mode:
            self._distance = span * 0.6
        else:
            fov_half = math.radians(22.5)
            self._distance = max(4.0, min(200.0, (span / 2.0) / math.tan(fov_half) * 1.1))
        self.changed.emit()

    def orbit(self, delta_az: float, delta_el: float) -> None:
        """Rotate the camera by (delta_az, delta_el) degrees."""
        self._azimuth  -= delta_az
        self._elevation = max(5.0, min(88.0, self._elevation + delta_el))
        self.changed.emit()

    def pan_right_drag(self, dx: float, dy: float, viewport_h: int) -> None:
        """Right-drag pan in orthographic top-down mode."""
        s = self._distance * 2.0 / max(viewport_h, 1)
        self._target[0] -= dx * s
        self._target[1] += dy * s
        self.changed.emit()

    def pan_middle_drag(self, dx: float, dy: float,
                        viewport_h: int, view: QMatrix4x4) -> None:
        """Middle-drag pan: move target in the ground plane."""
        if self._ortho_mode:
            s = self._distance * 2.0 / max(viewport_h, 1)
            self._target[0] -= dx * s
            self._target[1] += dy * s
        else:
            right = QVector3D(view.row(0))
            fwd_flat = QVector3D(
                -math.cos(math.radians(self._elevation)) * math.cos(math.radians(self._azimuth)),
                -math.cos(math.radians(self._elevation)) * math.sin(math.radians(self._azimuth)),
                0.0,
            )
            pan_speed = self._distance * 0.0015
            self._target[0] += (-right.x() * dx + fwd_flat.x() * dy) * pan_speed
            self._target[1] += (-right.y() * dx + fwd_flat.y() * dy) * pan_speed
        self.changed.emit()

    def zoom(self, factor: float) -> None:
        """Multiply camera distance by factor, clamped to [2, 200]."""
        self._distance = max(2.0, min(200.0, self._distance * factor))
        self.changed.emit()

    def set_ortho_mode(self, enabled: bool) -> None:
        self._ortho_mode = enabled
        self.changed.emit()

    def set_ortho_proj(self, enabled: bool) -> None:
        self._ortho_proj = enabled
        self.changed.emit()

    def set_pan_speed(self, speed: float) -> None:
        self._pan_speed = speed

    def key_press(self, key: Qt.Key) -> None:
        """Handle a WASD key press — starts smooth pan timer if needed."""
        self._pan_keys.add(key)
        if not self._pan_timer.isActive():
            self._pan_timer.start()

    def key_release(self, key: Qt.Key) -> None:
        """Handle a WASD key release — stops timer when no keys remain."""
        self._pan_keys.discard(key)
        if not self._pan_keys:
            self._pan_timer.stop()

    # ------------------------------------------------------------------
    # Internal pan tick
    # ------------------------------------------------------------------

    def _on_pan_tick(self) -> None:
        """Called at ~60 fps while any WASD key is held; pans the camera target."""
        speed = self._distance * self._pan_speed

        if self._ortho_mode:
            if Qt.Key_W in self._pan_keys: self._target[1] += speed
            if Qt.Key_S in self._pan_keys: self._target[1] -= speed
            if Qt.Key_A in self._pan_keys: self._target[0] -= speed
            if Qt.Key_D in self._pan_keys: self._target[0] += speed
        else:
            az = math.radians(self._azimuth)
            right_x, right_y =  math.sin(az), -math.cos(az)
            fwd_x,   fwd_y   = -math.cos(az), -math.sin(az)

            if Qt.Key_W in self._pan_keys:
                self._target[0] += fwd_x * speed
                self._target[1] += fwd_y * speed
            if Qt.Key_S in self._pan_keys:
                self._target[0] -= fwd_x * speed
                self._target[1] -= fwd_y * speed
            if Qt.Key_A in self._pan_keys:
                self._target[0] += right_x * speed
                self._target[1] += right_y * speed
            if Qt.Key_D in self._pan_keys:
                self._target[0] -= right_x * speed
                self._target[1] -= right_y * speed

        self.changed.emit()
