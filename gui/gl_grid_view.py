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

# ---------------------------------------------------------------------------
# Shaders
# ---------------------------------------------------------------------------

_MESH_VERT = """\
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNorm;
uniform mat4 uMVP;
uniform vec3 uNormScale;
out vec3 vNorm;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vNorm = normalize(aNorm * uNormScale);
}
"""

_MESH_FRAG = """\
#version 330 core
in vec3 vNorm;
uniform vec3 uColor;
uniform float uAlpha;
out vec4 FragColor;
void main() {
    vec3 n = normalize(vNorm);
    float key  = max(dot(n, normalize(vec3(-0.3, -0.5, 1.0))), 0.0) * 0.60;
    float fill = max(dot(n, normalize(vec3( 0.8,  0.4, 0.3))), 0.0) * 0.25;
    float rim  = max(dot(n, normalize(vec3( 0.2,  0.9,-0.3))), 0.0) * 0.10;
    float i = clamp(0.20 + key + fill + rim, 0.0, 1.0);
    FragColor = vec4(uColor * i, uAlpha);
}
"""

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
# CPU-side geometry helpers
# ---------------------------------------------------------------------------

def _build_vdata(triangles: np.ndarray, rotation: int = 0) -> np.ndarray:
    """
    Build interleaved (pos xyz, norm xyz) float32 VBO data from a (N, 3, 3) array.

    Applies Z-axis rotation around (0.5, 0.5) in XY, computes flat per-face
    normals via cross product, and returns a flat (N*3*6,) float32 array.
    """
    tris = triangles.copy()  # (N, 3, 3)

    if rotation != 0:
        cx = tris[:, :, 0] - 0.5
        cy = tris[:, :, 1] - 0.5
        if rotation == 90:
            tris[:, :, 0] = 0.5 - cy
            tris[:, :, 1] = 0.5 + cx
        elif rotation == 180:
            tris[:, :, 0] = 1.0 - tris[:, :, 0]
            tris[:, :, 1] = 1.0 - tris[:, :, 1]
        else:  # 270
            tris[:, :, 0] = 0.5 + cy
            tris[:, :, 1] = 0.5 - cx

    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    norms = np.cross(v1 - v0, v2 - v0)          # (N, 3) flat normals
    lengths = np.linalg.norm(norms, axis=1, keepdims=True)
    degen = (lengths < 1e-12).squeeze(axis=1)
    lengths = np.where(lengths < 1e-12, 1.0, lengths)
    norms /= lengths
    norms[degen] = [0.0, 0.0, 1.0]

    # Expand normals to per-vertex and interleave with positions: (N, 3, 6)
    norms_exp = np.repeat(norms[:, np.newaxis, :], 3, axis=1)
    combined = np.concatenate([tris, norms_exp], axis=2)  # (N, 3, 6)
    return combined.reshape(-1).astype(np.float32)


def _upload_geometry(vdata: np.ndarray, n_attribs: int = 6) -> Tuple[int, int, int]:
    """Upload vertex data to GPU. Returns (vao, vbo, n_verts)."""
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)
    stride = n_attribs * 4
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
    if n_attribs > 3:
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
    glBindVertexArray(0)
    return vao, vbo, len(vdata) // n_attribs


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
    _DEFAULT_DIST = 28.0

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
        """Upload VBOs for every tile + rotation combination."""
        if not self._ready:
            # Store for later — initializeGL will call this
            self._pending_definitions = definitions
            return
        self.makeCurrent()
        self._mesh_cache.clear()
        for defn in definitions:
            for rot in (0, 90, 180, 270):
                self._upload_tile(defn, rot)
        self.doneCurrent()
        self.update()

    def set_pending_tile(self, definition: Optional[TileDefinition], rotation: int) -> None:
        self._pending_def = definition
        self._pending_rot = rotation
        self.update()

    def refresh(self) -> None:
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
                self.load_definitions(self._pending_definitions)
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
            ghost = PlacedTile(self._pending_def, gx, gy, self._pending_rot)
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
        key  = (defn.stl_path, pt.rotation)

        # Lazily build VBO if missing
        if key not in self._mesh_cache:
            if defn.view_triangles is not None and len(defn.view_triangles) > 0:
                self._upload_tile(defn, pt.rotation)
            else:
                return
        if key not in self._mesh_cache:
            return

        vao, _vbo, n_verts = self._mesh_cache[key]

        # Model = translate to grid cell + scale by real-world proportions
        model = QMatrix4x4()
        model.translate(float(pt.grid_x), float(pt.grid_y), 0.0)
        model.scale(float(pt.effective_w), float(pt.effective_h), float(defn.grid_z))

        mvp = proj * view * model
        mvp_arr = np.array(mvp.data(), dtype=np.float32)

        # Normal scale = inverse of scale factors (no rotation in model)
        ns = (1.0 / pt.effective_w, 1.0 / pt.effective_h, 1.0 / max(defn.grid_z, 0.001))

        glUniformMatrix4fv(self._u_mvp,   1, GL_FALSE, mvp_arr)
        glUniform3f(self._u_ns,   *ns)
        glUniform3f(self._u_col,  defn.color.redF(), defn.color.greenF(), defn.color.blueF())
        glUniform1f(self._u_alpha, alpha)

        glBindVertexArray(vao)
        glDrawArrays(GL_TRIANGLES, 0, n_verts)
        glBindVertexArray(0)

    # ------------------------------------------------------------------
    # GPU resource management
    # ------------------------------------------------------------------

    def _upload_tile(self, defn: TileDefinition, rotation: int) -> None:
        """Build and cache a VAO for (defn, rotation)."""
        if defn.view_triangles is None or len(defn.view_triangles) == 0:
            return
        vdata = _build_vdata(defn.view_triangles, rotation)
        if len(vdata) == 0:
            return
        self._mesh_cache[(defn.stl_path, rotation)] = _upload_geometry(vdata, 6)

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

    def _ray_to_grid(self, sx: int, sy: int) -> Tuple[int, int]:
        w, h = max(self.width(), 1), max(self.height(), 1)
        proj, view = self._get_proj_view()
        inv_pv, ok = (proj * view).inverted()
        if not ok:
            return -1, -1

        ndx = (2.0 * sx / w) - 1.0
        ndy = 1.0 - (2.0 * sy / h)

        near4 = inv_pv * QVector4D(ndx, ndy, -1.0, 1.0)
        far4  = inv_pv * QVector4D(ndx, ndy,  1.0, 1.0)

        near = QVector3D(near4.x() / near4.w(), near4.y() / near4.w(), near4.z() / near4.w())
        far  = QVector3D(far4.x()  / far4.w(),  far4.y()  / far4.w(),  far4.z()  / far4.w())

        rd = far - near
        if abs(rd.z()) < 1e-6:
            return -1, -1
        t = -near.z() / rd.z()
        if t < 0:
            return -1, -1

        hx = near.x() + t * rd.x()
        hy = near.y() + t * rd.y()
        return int(math.floor(hx)), int(math.floor(hy))

    # ------------------------------------------------------------------
    # Mouse / keyboard events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.pos()
        self._drag_button = event.button()

        if event.button() == Qt.LeftButton:
            gx, gy = self._ray_to_grid(event.x(), event.y())
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
            gx, gy = self._ray_to_grid(event.x(), event.y())
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
        vs = self._compile(vert_src, GL_VERTEX_SHADER)
        fs = self._compile(frag_src, GL_FRAGMENT_SHADER)
        prog = glCreateProgram()
        glAttachShader(prog, vs)
        glAttachShader(prog, fs)
        glLinkProgram(prog)
        if not glGetProgramiv(prog, GL_LINK_STATUS):
            err = glGetProgramInfoLog(prog)
            raise RuntimeError(f"Shader link: {err}")
        glDeleteShader(vs)
        glDeleteShader(fs)
        return prog

    @staticmethod
    def _compile(src: str, kind: int) -> int:
        s = glCreateShader(kind)
        glShaderSource(s, src)
        glCompileShader(s)
        if not glGetShaderiv(s, GL_COMPILE_STATUS):
            err = glGetShaderInfoLog(s)
            raise RuntimeError(f"Shader compile: {err}")
        return s
