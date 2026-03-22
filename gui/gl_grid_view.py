"""
3-D dungeon grid view — QOpenGLWidget with interactive orbit camera.

Controls
--------
Left-click          Place selected tile at the hovered grid cell
Right-click         Remove tile at the hovered grid cell
Right-drag          Orbit camera (azimuth / elevation)
Middle-drag         Pan camera target
Scroll              Zoom (change camera distance)
R key               Rotate pending tile 90°
Delete key          Remove tile at last hovered cell
Home key            Reset camera to default position
"""
import ctypes
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QMatrix4x4, QVector3D, QVector4D
from PyQt5.QtWidgets import QOpenGLWidget, QMessageBox

try:
    from OpenGL.GL import (
        GL_ARRAY_BUFFER, GL_COLOR_BUFFER_BIT, GL_COMPILE_STATUS,
        GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_FALSE, GL_FLOAT,
        GL_FRAGMENT_SHADER, GL_LINES, GL_LINK_STATUS, GL_STATIC_DRAW,
        GL_TRIANGLES, GL_VERTEX_SHADER, GL_BLEND, GL_SRC_ALPHA,
        GL_ONE_MINUS_SRC_ALPHA,
        glAttachShader, glBindBuffer, glBindVertexArray, glBlendFunc,
        glBufferData, glClear, glClearColor, glCompileShader, glCreateProgram,
        glCreateShader, glDeleteBuffers, glDeleteShader, glDeleteVertexArrays,
        glDisable, glDrawArrays, glEnable, glEnableVertexAttribArray,
        glGenBuffers, glGenVertexArrays, glGetProgramInfoLog, glGetProgramiv,
        glGetShaderInfoLog, glGetShaderiv, glGetUniformLocation, glLinkProgram,
        glLineWidth, glShaderSource, glUniform1f, glUniform3f, glUniform4f,
        glUniformMatrix4fv, glUseProgram, glVertexAttribPointer, glViewport,
    )
    _GL_OK = True
except ImportError:
    _GL_OK = False

from models.grid_model import GridModel
from models.placed_tile import PlacedTile
from models.tile_definition import TileDefinition
from gui.gl_helpers import (
    MESH_VERT as _MESH_VERT, MESH_FRAG as _MESH_FRAG,
    build_vdata as _build_vdata, upload_geometry as _upload_geometry,
    build_program as _build_program_fn, compile_shader as _compile_fn,
)

# ---------------------------------------------------------------------------
# Flat shaders (grid / ground plane only — not shared with preview widget)
# ---------------------------------------------------------------------------

_FLAT_VERT = """\
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 uMVP;
void main() { gl_Position = uMVP * vec4(aPos, 1.0); }
"""

_FLAT_FRAG = """\
#version 330 core
uniform vec4 uColor;
out vec4 FragColor;
void main() { FragColor = uColor; }
"""


# ---------------------------------------------------------------------------
# GLGridView
# ---------------------------------------------------------------------------

class GLGridView(QOpenGLWidget):
    tile_place_requested  = pyqtSignal(int, int)
    tile_remove_requested = pyqtSignal(int, int)
    rotate_requested      = pyqtSignal()
    hover_cell_changed    = pyqtSignal(int, int)

    # Camera defaults
    _DEFAULT_AZ   = 45.0
    _DEFAULT_EL   = 55.0
    _DEFAULT_DIST = 56.0

    def __init__(self, grid_model: GridModel, parent=None) -> None:
        super().__init__(parent)
        self._model = grid_model

        # Camera spherical coords
        cx = grid_model.GRID_COLS / 2.0
        cy = grid_model.GRID_ROWS / 2.0
        self._target   = [cx, cy, 0.0]
        self._azimuth  = self._DEFAULT_AZ
        self._elevation= self._DEFAULT_EL
        self._distance = self._DEFAULT_DIST

        # Interaction
        self._last_mouse: Optional[QPoint] = None
        self._drag_button: Optional[int]   = None
        self._hover_cell: Tuple[int, int]  = (-1, -1)
        self._mouse_screen: Tuple[int, int] = (0, 0)

        # Pending placement
        self._pending_def: Optional[TileDefinition] = None
        self._pending_rot: int = 0

        # GPU resources (populated in initializeGL / load_definitions)
        self._mesh_prog  = 0
        self._flat_prog  = 0
        self._mesh_cache: Dict[Tuple[str, int], Tuple[int, int, int]] = {}
        self._ground_vao = self._ground_vbo = self._ground_n = 0
        self._grid_vao   = self._grid_vbo   = self._grid_n   = 0
        self._ready      = False  # True after initializeGL succeeds

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------
    # Public API (called by MainWindow)
    # ------------------------------------------------------------------

    def load_definitions(self, definitions: List[TileDefinition]) -> None:
        """Upload a VBO for each tile (single canonical orientation)."""
        if not self._ready:
            self._pending_definitions = definitions
            return
        self.makeCurrent()
        self._mesh_cache.clear()
        for defn in definitions:
            self._upload_tile(defn)
        self.doneCurrent()
        self.update()

    def set_pending_tile(self, definition: Optional[TileDefinition], rotation: int) -> None:
        self._pending_def = definition
        self._pending_rot = rotation
        # Recompute hover so the tile pivots around the current cursor position
        mx, my = self._mouse_screen
        self._hover_cell = self._compute_hover_cell(mx, my)
        self.update()

    def refresh(self) -> None:
        self.update()

    def rebuild_grid_geometry(self) -> None:
        """Rebuild ground/grid VBOs after a grid resize and reset the camera."""
        if not self._ready:
            return
        self.makeCurrent()
        if self._ground_vao:
            glDeleteVertexArrays(1, [self._ground_vao])
            glDeleteBuffers(1, [self._ground_vbo])
        if self._grid_vao:
            glDeleteVertexArrays(1, [self._grid_vao])
            glDeleteBuffers(1, [self._grid_vbo])
        self._build_static_geometry()
        self._reset_camera()
        self.doneCurrent()
        self.update()

    def add_definitions(self, definitions: List[TileDefinition]) -> None:
        """Upload VBOs for new definitions without clearing existing cached tiles."""
        if not self._ready:
            existing = getattr(self, '_pending_definitions', [])
            self._pending_definitions = existing + list(definitions)
            return
        self.makeCurrent()
        for defn in definitions:
            if defn.stl_path not in self._mesh_cache:
                self._upload_tile(defn)
        self.doneCurrent()
        self.update()

    # ------------------------------------------------------------------
    # QOpenGLWidget lifecycle
    # ------------------------------------------------------------------

    def initializeGL(self) -> None:
        if not _GL_OK:
            QMessageBox.critical(self, "OpenGL error", "PyOpenGL is not installed.\nRun launch.bat to install dependencies.")
            return
        try:
            self._mesh_prog = self._build_program(_MESH_VERT, _MESH_FRAG)
            self._flat_prog = self._build_program(_FLAT_VERT, _FLAT_FRAG)

            # Uniform locations — mesh
            p = self._mesh_prog
            self._u_mvp   = glGetUniformLocation(p, b"uMVP")
            self._u_ns    = glGetUniformLocation(p, b"uNormScale")
            self._u_col   = glGetUniformLocation(p, b"uColor")
            self._u_alpha = glGetUniformLocation(p, b"uAlpha")
            self._u_rotz  = glGetUniformLocation(p, b"uRotZ")

            # Uniform locations — flat
            p = self._flat_prog
            self._u_flat_mvp = glGetUniformLocation(p, b"uMVP")
            self._u_flat_col = glGetUniformLocation(p, b"uColor")

            glEnable(GL_DEPTH_TEST)
            glClearColor(0.10, 0.10, 0.12, 1.0)

            self._build_static_geometry()
            self._ready = True

            # Upload any definitions that arrived before GL was ready
            if hasattr(self, '_pending_definitions'):
                self.add_definitions(self._pending_definitions)
                del self._pending_definitions

        except Exception as exc:
            QMessageBox.critical(self, "OpenGL init error", str(exc))

    def resizeGL(self, w: int, h: int) -> None:
        glViewport(0, 0, w, h)

    def paintGL(self) -> None:
        if not self._ready:
            return
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        proj, view = self._get_proj_view()
        pv = proj * view
        pv_arr = np.array(pv.data(), dtype=np.float32)

        # --- Ground plane and grid lines ---
        glUseProgram(self._flat_prog)
        glUniformMatrix4fv(self._u_flat_mvp, 1, GL_FALSE, pv_arr)
        glUniform4f(self._u_flat_col, 0.22, 0.22, 0.25, 1.0)
        glBindVertexArray(self._ground_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._ground_n)

        glUniform4f(self._u_flat_col, 0.45, 0.45, 0.50, 1.0)
        glLineWidth(1.0)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_LINES, 0, self._grid_n)
        glBindVertexArray(0)

        # --- Placed tiles ---
        glUseProgram(self._mesh_prog)
        for pt in self._model.all_placed():
            self._draw_tile(pt, proj, view, alpha=1.0)

        # --- Ghost preview ---
        gx, gy = self._hover_cell
        if self._pending_def is not None and gx >= 0:
            z_off = self._model.top_z_at(gx, gy)
            ghost = PlacedTile(self._pending_def, gx, gy, self._pending_rot, z_offset=z_off)
            if self._model.can_place(ghost):
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                self._draw_tile(ghost, proj, view, alpha=0.45)
                glDisable(GL_BLEND)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_tile(self, pt: PlacedTile, proj: QMatrix4x4, view: QMatrix4x4, alpha: float) -> None:
        defn = pt.definition
        key  = defn.stl_path

        # Lazily build VBO if missing
        if key not in self._mesh_cache:
            if defn.view_triangles is not None and len(defn.view_triangles) > 0:
                self._upload_tile(defn)
            else:
                return
        if key not in self._mesh_cache:
            return

        vao, _vbo, n_verts = self._mesh_cache[key]

        ew = float(pt.effective_w)
        eh = float(pt.effective_h)
        gz = float(defn.grid_z)

        # Model = translate to grid cell, scale to tile proportions, rotate in-place
        model = QMatrix4x4()
        model.translate(float(pt.grid_x), float(pt.grid_y), pt.z_offset)
        model.scale(ew, eh, gz)
        if pt.rotation != 0:
            model.translate(0.5, 0.5, 0.0)
            model.rotate(float(pt.rotation), 0.0, 0.0, 1.0)
            model.translate(-0.5, -0.5, 0.0)

        mvp = proj * view * model
        mvp_arr = np.array(mvp.data(), dtype=np.float32)

        ns = (1.0 / ew, 1.0 / eh, 1.0 / max(gz, 0.001))

        glUniformMatrix4fv(self._u_mvp,   1, GL_FALSE, mvp_arr)
        glUniform1f(self._u_rotz, math.radians(pt.rotation))
        glUniform3f(self._u_ns,   *ns)
        glUniform3f(self._u_col,  defn.color.redF(), defn.color.greenF(), defn.color.blueF())
        glUniform1f(self._u_alpha, alpha)

        glBindVertexArray(vao)
        glDrawArrays(GL_TRIANGLES, 0, n_verts)
        glBindVertexArray(0)

    # ------------------------------------------------------------------
    # GPU resource management
    # ------------------------------------------------------------------

    def _upload_tile(self, defn: TileDefinition) -> None:
        """Build and cache a VAO for defn (canonical orientation; rotation is matrix-driven)."""
        if defn.view_triangles is None or len(defn.view_triangles) == 0:
            return
        vdata = _build_vdata(defn.view_triangles)
        if len(vdata) == 0:
            return
        self._mesh_cache[defn.stl_path] = _upload_geometry(vdata, 6)

    def _build_static_geometry(self) -> None:
        """Build ground plane and grid line geometry."""
        cols = self._model.GRID_COLS
        rows = self._model.GRID_ROWS
        z = -0.005  # just below tile floor

        # Ground quad (2 triangles)
        ground = np.array([
            0.0,  0.0,  z,
            cols, 0.0,  z,
            cols, rows, z,
            0.0,  0.0,  z,
            cols, rows, z,
            0.0,  rows, z,
        ], dtype=np.float32)
        self._ground_vao, self._ground_vbo, self._ground_n = _upload_geometry(ground, 3)

        # Grid lines
        verts: list = []
        gz = z + 0.001
        for i in range(cols + 1):
            verts += [float(i), 0.0, gz, float(i), float(rows), gz]
        for j in range(rows + 1):
            verts += [0.0, float(j), gz, float(cols), float(j), gz]
        grid = np.array(verts, dtype=np.float32)
        self._grid_vao, self._grid_vbo, self._grid_n = _upload_geometry(grid, 3)

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _eye_pos(self) -> QVector3D:
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

    def _get_proj_view(self) -> Tuple[QMatrix4x4, QMatrix4x4]:
        w, h = max(self.width(), 1), max(self.height(), 1)
        proj = QMatrix4x4()
        proj.perspective(45.0, w / h, 0.05, 500.0)

        view = QMatrix4x4()
        eye = self._eye_pos()
        # Use world up = (0,0,1), fall back to (0,1,0) at extreme elevation
        up = QVector3D(0.0, 0.0, 1.0) if self._elevation < 88.0 else QVector3D(0.0, 1.0, 0.0)
        view.lookAt(eye, QVector3D(*self._target), up)
        return proj, view

    def _reset_camera(self) -> None:
        cx = self._model.GRID_COLS / 2.0
        cy = self._model.GRID_ROWS / 2.0
        self._target   = [cx, cy, 0.0]
        self._azimuth  = self._DEFAULT_AZ
        self._elevation= self._DEFAULT_EL
        self._distance = self._DEFAULT_DIST
        self.update()

    # ------------------------------------------------------------------
    # Ray casting: screen → grid cell on Z=0 plane
    # ------------------------------------------------------------------

    def _ray_to_world(self, sx: int, sy: int, z_plane: float = 0.0) -> Optional[Tuple[float, float]]:
        """Cast a ray from screen pixel (sx, sy) to world Z=z_plane.
        Returns continuous (hx, hy) or None on miss."""
        w, h = max(self.width(), 1), max(self.height(), 1)
        proj, view = self._get_proj_view()
        inv_pv, ok = (proj * view).inverted()
        if not ok:
            return None

        ndx = (2.0 * sx / w) - 1.0
        ndy = 1.0 - (2.0 * sy / h)

        near4 = inv_pv * QVector4D(ndx, ndy, -1.0, 1.0)
        far4  = inv_pv * QVector4D(ndx, ndy,  1.0, 1.0)

        near = QVector3D(near4.x() / near4.w(), near4.y() / near4.w(), near4.z() / near4.w())
        far  = QVector3D(far4.x()  / far4.w(),  far4.y()  / far4.w(),  far4.z()  / far4.w())

        rd = far - near
        if abs(rd.z()) < 1e-6:
            return None
        t = (z_plane - near.z()) / rd.z()
        if t < 0:
            return None

        return near.x() + t * rd.x(), near.y() + t * rd.y()

    def _ray_to_grid(self, sx: int, sy: int) -> Tuple[int, int]:
        world = self._ray_to_world(sx, sy, 0.0)
        if world is None:
            return -1, -1
        return int(math.floor(world[0])), int(math.floor(world[1]))

    def _compute_hover_cell(self, mx: int, my: int) -> Tuple[int, int]:
        """Return the grid origin for the pending tile centered on the cursor.
        Falls back to raw floor position when no tile is pending."""
        world = self._ray_to_world(mx, my, 0.0)
        if world is None:
            return -1, -1
        hx, hy = world
        if self._pending_def is None:
            return int(math.floor(hx)), int(math.floor(hy))
        if self._pending_rot in (90, 270):
            ew = float(self._pending_def.grid_h)
            eh = float(self._pending_def.grid_w)
        else:
            ew = float(self._pending_def.grid_w)
            eh = float(self._pending_def.grid_h)
        gx = int(round(hx - ew / 2.0))
        gy = int(round(hy - eh / 2.0))
        return gx, gy

    # ------------------------------------------------------------------
    # Mouse / keyboard events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.pos()
        self._drag_button = event.button()

        if event.button() == Qt.LeftButton:
            gx, gy = self._hover_cell
            if gx >= 0:
                self.tile_place_requested.emit(gx, gy)
        elif event.button() == Qt.RightButton:
            # Right-click with no movement = remove tile
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._last_mouse is None:
            self._last_mouse = event.pos()

        dx = event.x() - self._last_mouse.x()
        dy = event.y() - self._last_mouse.y()
        self._last_mouse = event.pos()

        if self._drag_button == Qt.RightButton and (abs(dx) > 0 or abs(dy) > 0):
            # Orbit
            self._azimuth  -= dx * 0.4
            self._elevation = max(5.0, min(88.0, self._elevation + dy * 0.4))
            self.update()
        elif self._drag_button == Qt.MiddleButton:
            # Pan: move target in the ground plane
            _, view = self._get_proj_view()
            # Right vector from view matrix (row 0)
            right = QVector3D(view.row(0))
            fwd_flat = QVector3D(
                -math.cos(math.radians(self._elevation)) * math.cos(math.radians(self._azimuth)),
                -math.cos(math.radians(self._elevation)) * math.sin(math.radians(self._azimuth)),
                0.0,
            )
            pan_speed = self._distance * 0.0015
            self._target[0] += (-right.x() * dx + fwd_flat.x() * dy) * pan_speed
            self._target[1] += (-right.y() * dx + fwd_flat.y() * dy) * pan_speed
            self.update()
        else:
            # Update hover ghost
            self._mouse_screen = (event.x(), event.y())
            gx, gy = self._compute_hover_cell(event.x(), event.y())
            if (gx, gy) != self._hover_cell:
                self._hover_cell = (gx, gy)
                self.hover_cell_changed.emit(gx, gy)
                self.update()

    def mouseReleaseEvent(self, event) -> None:
        # Short right-click (no drag) = remove tile
        if event.button() == Qt.RightButton and hasattr(self, '_drag_start'):
            d = event.pos() - self._drag_start
            if abs(d.x()) < 5 and abs(d.y()) < 5:
                gx, gy = self._ray_to_grid(event.x(), event.y())
                if gx >= 0:
                    self.tile_remove_requested.emit(gx, gy)
            del self._drag_start
        self._drag_button = None
        self._last_mouse  = None

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        self._distance = max(2.0, min(200.0, self._distance * factor))
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_R:
            self.rotate_requested.emit()
        elif event.key() == Qt.Key_Delete:
            gx, gy = self._hover_cell
            if gx >= 0:
                self.tile_remove_requested.emit(gx, gy)
        elif event.key() == Qt.Key_Home:
            self._reset_camera()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Shader compilation
    # ------------------------------------------------------------------

    def _build_program(self, vert_src: str, frag_src: str) -> int:
        return _build_program_fn(vert_src, frag_src)

    @staticmethod
    def _compile(src: str, kind: int) -> int:
        return _compile_fn(src, kind)
