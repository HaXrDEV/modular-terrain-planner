"""
Standalone 3D tile preview widget embedded in the palette panel.

Shows the selected TileDefinition rendered with the same shaders as the main
grid view. Left-drag orbits the camera; scroll wheel zooms.
"""
import math
from typing import Optional, Tuple

import numpy as np
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QMatrix4x4, QVector3D
from PyQt5.QtWidgets import QOpenGLWidget

try:
    from OpenGL.GL import (
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_FALSE,
        GL_TRIANGLES,
        glBindVertexArray, glClear, glClearColor, glDeleteBuffers,
        glDeleteVertexArrays, glDrawArrays, glEnable, glGetUniformLocation,
        glUniform1f, glUniform3f, glUniformMatrix4fv, glUseProgram, glViewport,
    )
    _GL_OK = True
except ImportError:
    _GL_OK = False

from gui.gl_helpers import (
    MESH_VERT, MESH_FRAG,
    build_vdata, upload_geometry, build_program,
)
from models.tile_definition import TileDefinition


class TilePreviewWidget(QOpenGLWidget):
    """3D preview of a single tile; embedded in PalettePanel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._defn: Optional[TileDefinition] = None
        self._rotation: int = 0

        # Camera spherical coords
        self._target   = [0.5, 0.5, 0.0]
        self._azimuth  = 35.0
        self._elevation= 40.0
        self._distance = 2.5

        # Mouse interaction
        self._last_mouse: Optional[QPoint] = None

        # GL resources
        self._mesh_prog: int = 0
        self._u_mvp    = None
        self._u_ns     = None
        self._u_col    = None
        self._u_alpha  = None
        self._vao: int = 0
        self._vbo: int = 0
        self._n_verts: int = 0

        self._ready          = False
        self._pending_upload = False

        self.setFixedHeight(200)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tile(self, defn: Optional[TileDefinition], rotation: int = 0) -> None:
        self._defn     = defn
        self._rotation = rotation
        if defn is not None:
            self._auto_fit_camera(defn)
        if self._ready:
            self._rebuild_geometry()
        else:
            self._pending_upload = True
        self.update()

    # ------------------------------------------------------------------
    # QOpenGLWidget lifecycle
    # ------------------------------------------------------------------

    def initializeGL(self) -> None:
        if not _GL_OK:
            return
        try:
            self._mesh_prog = build_program(MESH_VERT, MESH_FRAG)
            p = self._mesh_prog
            self._u_mvp   = glGetUniformLocation(p, b"uMVP")
            self._u_ns    = glGetUniformLocation(p, b"uNormScale")
            self._u_col   = glGetUniformLocation(p, b"uColor")
            self._u_alpha = glGetUniformLocation(p, b"uAlpha")

            glEnable(GL_DEPTH_TEST)
            glClearColor(0.13, 0.13, 0.15, 1.0)

            self._ready = True

            if self._pending_upload:
                self._rebuild_geometry()
                self._pending_upload = False

        except Exception as exc:
            print(f"[TilePreviewWidget] GL init error: {exc}")

    def resizeGL(self, w: int, h: int) -> None:
        glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        if not self._ready:
            return
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        if self._vao == 0 or self._n_verts == 0 or self._defn is None:
            return

        proj, view = self._get_proj_view()

        # Scale mesh from [0,1]³ to actual grid-cell proportions
        gw = float(self._defn.grid_w)
        gh = float(self._defn.grid_h)
        gz = float(self._defn.grid_z)
        model = QMatrix4x4()
        model.scale(gw, gh, gz)

        mvp = proj * view * model
        mvp_arr = np.array(mvp.data(), dtype=np.float32)

        glUseProgram(self._mesh_prog)
        glUniformMatrix4fv(self._u_mvp, 1, GL_FALSE, mvp_arr)
        glUniform3f(self._u_ns, 1.0 / gw, 1.0 / gh, 1.0 / max(gz, 0.001))
        glUniform3f(self._u_col,
                    self._defn.color.redF(),
                    self._defn.color.greenF(),
                    self._defn.color.blueF())
        glUniform1f(self._u_alpha, 1.0)

        glBindVertexArray(self._vao)
        glDrawArrays(GL_TRIANGLES, 0, self._n_verts)
        glBindVertexArray(0)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _rebuild_geometry(self) -> None:
        self.makeCurrent()

        # Release old GPU resources
        if self._vao:
            glDeleteVertexArrays(1, [self._vao])
            glDeleteBuffers(1, [self._vbo])
        self._vao = self._vbo = self._n_verts = 0

        if (self._defn is None
                or self._defn.view_triangles is None
                or len(self._defn.view_triangles) == 0):
            self.doneCurrent()
            return

        vdata = build_vdata(self._defn.view_triangles, self._rotation)
        if len(vdata) > 0:
            self._vao, self._vbo, self._n_verts = upload_geometry(vdata, 6)

        self.doneCurrent()

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _auto_fit_camera(self, defn: TileDefinition) -> None:
        """Set camera target and distance to frame the tile's actual proportions."""
        gw, gh, gz = float(defn.grid_w), float(defn.grid_h), float(defn.grid_z)
        self._target = [gw / 2.0, gh / 2.0, gz / 2.0]
        half_diag = math.sqrt(gw ** 2 + gh ** 2 + gz ** 2) / 2.0
        fov_half = math.radians(22.5)   # half of 45° FOV
        self._distance = max(1.5, min(20.0, (half_diag / math.tan(fov_half)) * 1.15))

    def _get_proj_view(self) -> Tuple[QMatrix4x4, QMatrix4x4]:
        w = max(self.width(), 1)
        h = max(self.height(), 1)

        proj = QMatrix4x4()
        proj.perspective(45.0, w / h, 0.01, 50.0)

        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)
        dx = self._distance * math.cos(el) * math.cos(az)
        dy = self._distance * math.cos(el) * math.sin(az)
        dz = self._distance * math.sin(el)

        eye = QVector3D(
            self._target[0] + dx,
            self._target[1] + dy,
            self._target[2] + dz,
        )
        view = QMatrix4x4()
        up = QVector3D(0, 0, 1) if self._elevation < 88.0 else QVector3D(0, 1, 0)
        view.lookAt(eye, QVector3D(*self._target), up)
        return proj, view

    # ------------------------------------------------------------------
    # Mouse / keyboard events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._last_mouse is None:
            self._last_mouse = event.pos()
            return
        if event.buttons() & Qt.LeftButton:
            dx = event.x() - self._last_mouse.x()
            dy = event.y() - self._last_mouse.y()
            self._azimuth  -= dx * 0.5
            self._elevation = max(5.0, min(88.0, self._elevation + dy * 0.5))
            self.update()
        self._last_mouse = event.pos()

    def mouseReleaseEvent(self, event) -> None:
        self._last_mouse = None

    def wheelEvent(self, event) -> None:
        factor = 0.9 if event.angleDelta().y() > 0 else 1.1
        self._distance = max(0.5, min(20.0, self._distance * factor))
        self.update()
