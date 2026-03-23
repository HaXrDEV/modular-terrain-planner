"""
3-D dungeon grid view — QOpenGLWidget with interactive orbit camera.

Controls
--------
Left-click          Place selected tile at the hovered grid cell
Ctrl + Left-click   Place tile freely (no grid snap, overlaps allowed)
Right-click         Remove tile at the hovered grid cell
Right-drag          Orbit camera (azimuth / elevation)
Middle-drag         Pan camera target
Scroll              Zoom (change camera distance)
R key               Rotate pending tile 90°
W/A/S/D keys        Pan camera forward / left / back / right
Delete key          Remove tile at last hovered cell
Home key            Reset camera to default position
"""
import ctypes
import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QMatrix4x4, QVector3D, QVector4D
from PyQt5.QtWidgets import QOpenGLWidget, QMessageBox

try:
    from OpenGL.GL import (
        GL_ARRAY_BUFFER, GL_COLOR_BUFFER_BIT, GL_COMPILE_STATUS,
        GL_BACK, GL_FRONT, GL_CULL_FACE,
        GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_DYNAMIC_DRAW, GL_FALSE, GL_FLOAT,
        GL_STENCIL_BUFFER_BIT, GL_STENCIL_TEST,
        GL_ALWAYS, GL_NOTEQUAL, GL_KEEP, GL_REPLACE, GL_TRUE,
        GL_POLYGON_OFFSET_FILL,
        glColorMask, glPolygonOffset, glStencilFunc, glStencilOp,
        GL_FRAGMENT_SHADER, GL_LINE_LOOP, GL_LINES, GL_LINK_STATUS, GL_STATIC_DRAW,
        GL_TRIANGLES, GL_VERTEX_SHADER, GL_BLEND, GL_SRC_ALPHA,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_TEXTURE_2D, GL_TEXTURE0, GL_LINEAR, GL_CLAMP_TO_EDGE,
        GL_RGBA, GL_UNSIGNED_BYTE, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
        GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
        glAttachShader, glBindBuffer, glBindVertexArray, glBlendFunc,
        glBufferData, glClear, glClearColor, glCompileShader, glCreateProgram,
        glCreateShader, glDeleteBuffers, glDeleteShader, glDeleteVertexArrays,
        glCullFace, glDepthMask, glDisable, glDrawArrays, glDrawArraysInstanced, glEnable,
        glEnableVertexAttribArray,
        glGenBuffers, glGenVertexArrays, glGetProgramInfoLog, glGetProgramiv,
        glGetShaderInfoLog, glGetShaderiv, glGetUniformLocation, glLinkProgram,
        glLineWidth, glShaderSource, glUniform1f, glUniform1i, glUniform3f,
        glUniform4f, glUniformMatrix4fv, glUseProgram, glVertexAttribDivisor,
        glVertexAttribPointer,
        glViewport, glGenTextures, glBindTexture, glTexImage2D, glTexParameteri,
        glDeleteTextures, glActiveTexture,
    )
    _GL_OK = True
except ImportError:
    _GL_OK = False

from models.grid_model import GridModel
from models.placed_tile import PlacedTile
from models.tile_definition import TileDefinition
from gui.gl_helpers import (
    MESH_VERT as _MESH_VERT, MESH_FRAG as _MESH_FRAG,
    INST_VERT as _INST_VERT, INST_FRAG as _INST_FRAG,
    OUTLINE_VERT as _OUTLINE_VERT, OUTLINE_FRAG as _OUTLINE_FRAG,
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

_TEX_VERT = """\
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 uMVP;
uniform vec4 uTexRect;
out vec2 vUV;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vUV = vec2((aPos.x - uTexRect.x) / uTexRect.z,
               (aPos.y - uTexRect.y) / uTexRect.w);
}
"""

_TEX_FRAG = """\
#version 330 core
in vec2 vUV;
uniform sampler2D uTex;
out vec4 FragColor;
void main() { FragColor = texture(uTex, vUV); }
"""


# ---------------------------------------------------------------------------
# Ray–mesh picking helpers (module-level, CPU/numpy)
# ---------------------------------------------------------------------------

def _ray_aabb(origin: np.ndarray, direction: np.ndarray,
              lo: np.ndarray, hi: np.ndarray) -> bool:
    """Slab method AABB test. Returns True if the ray hits [lo, hi]."""
    t_min, t_max = -np.inf, np.inf
    for i in range(3):
        d = direction[i]
        if abs(d) < 1e-10:
            if origin[i] < lo[i] or origin[i] > hi[i]:
                return False
        else:
            t1 = (lo[i] - origin[i]) / d
            t2 = (hi[i] - origin[i]) / d
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
    return t_max >= max(t_min, 0.0)


def _ray_triangles_min_t(origin: np.ndarray, direction: np.ndarray,
                         triangles: np.ndarray) -> Optional[float]:
    """Vectorised Möller–Trumbore over (N,3,3) float32 array.
    Returns the smallest positive t, or None if no hit."""
    EPS = 1e-7
    v0 = triangles[:, 0].astype(np.float64)
    v1 = triangles[:, 1].astype(np.float64)
    v2 = triangles[:, 2].astype(np.float64)

    e1 = v1 - v0
    e2 = v2 - v0

    h = np.cross(direction, e2)                       # (N, 3)
    a = np.einsum('ni,ni->n', e1, h)                  # (N,)

    valid = np.abs(a) > EPS
    f = np.where(valid, 1.0 / np.where(valid, a, 1.0), 0.0)

    s  = origin - v0                                  # (N, 3)
    u  = f * np.einsum('ni,ni->n', s, h)

    q  = np.cross(s, e1)                              # (N, 3)
    v  = f * np.einsum('i,ni->n', direction, q)

    t  = f * np.einsum('ni,ni->n', e2, q)

    hit = valid & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > EPS)
    if not np.any(hit):
        return None
    return float(np.min(t[hit]))


# ---------------------------------------------------------------------------
# GLGridView
# ---------------------------------------------------------------------------

class GLGridView(QOpenGLWidget):
    tile_place_requested       = pyqtSignal(float, float)
    tile_remove_requested      = pyqtSignal(object)   # emits PlacedTile
    tile_pickup_requested      = pyqtSignal(object)   # emits PlacedTile
    tiles_move_requested       = pyqtSignal(object)   # emits list of (PlacedTile, new_gx, new_gy)
    paste_place_requested      = pyqtSignal(float, float)  # cx, cy (snapped grid coords)
    selection_rotate_requested = pyqtSignal()
    rotate_requested           = pyqtSignal()
    deselect_requested         = pyqtSignal()
    hover_cell_changed         = pyqtSignal(int, int)
    ground_image_rect_changed  = pyqtSignal(list)

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
        self._hover_cell: Tuple[int, int]     = (-1, -1)
        self._hover_pos:  Tuple[float, float] = (-1.0, -1.0)
        self._mouse_screen: Tuple[int, int]   = (0, 0)

        # WASD smooth pan
        self._pan_speed: float = 0.008   # cells per tick per unit of distance
        self._pan_keys: set = set()
        self._pan_timer = QTimer(self)
        self._pan_timer.setInterval(16)   # ~60 fps
        self._pan_timer.timeout.connect(self._on_pan_tick)

        # Image drag state (Alt + left-drag)
        self._img_dragging: bool = False
        self._img_drag_start_world: Optional[Tuple[float, float]] = None
        self._img_drag_start_rect: Optional[list] = None

        # Selection & move
        self._selection: set = set()
        self._box_start_screen: Optional[Tuple[int, int]] = None
        self._box_end_screen: Optional[Tuple[int, int]] = None
        self._move_world_start: Optional[Tuple[float, float]] = None
        self._move_snap_offsets: dict = {}
        self._move_rotations: dict = {}        # {PlacedTile: rotation override}
        self._move_dragging: bool = False
        self._move_delta: Tuple[float, float] = (0.0, 0.0)

        # Pending placement
        self._pending_def: Optional[TileDefinition] = None
        self._pending_rot: int = 0

        # Paste ghost buffer: list of (TileDefinition, rel_x, rel_y, rotation, rel_z)
        self._paste_buffer: Optional[list] = None

        # GPU resources (populated in initializeGL / load_definitions)
        self._mesh_prog    = 0
        self._flat_prog    = 0
        self._tex_prog     = 0
        self._inst_prog    = 0   # instanced mesh shader
        self._outline_prog = 0   # solid-colour back-face extrusion outline
        # Caches keyed by (stl_path, lod_level).  lod_level 0 = full quality.
        # _mesh_cache: ghost/preview draws (per-draw uniforms, _mesh_prog)
        # _inst_cache: instanced placed-tile draws (_inst_prog)
        self._mesh_cache: Dict[Tuple[str, int], Tuple[int, int, int]] = {}
        self._inst_cache: Dict[Tuple[str, int], Tuple[int, int, int]] = {}
        self._ground_vao = self._ground_vbo = self._ground_n = 0
        self._grid_vao   = self._grid_vbo   = self._grid_n   = 0
        self._sel_vao    = self._sel_vbo    = 0   # scratch VAO for selection highlights
        self._ready      = False  # True after initializeGL succeeds
        self._instances_dirty: bool = True   # rebuild per-instance buffers next paintGL
        self._inst_counts: Dict[str, int] = {}
        self._u_inst_pv  = 0
        self._bg           = (0.10, 0.10, 0.12)  # void background colour
        self._ground_col   = (0.22, 0.22, 0.25)  # ground plane fill
        self._grid_col     = (0.45, 0.45, 0.50)  # grid lines

        # Ground image texture
        self._tex_id:   int  = 0
        self._img_rect: list = [0.0, 0.0,
                                float(grid_model.GRID_COLS),
                                float(grid_model.GRID_ROWS)]
        self._img_vao = self._img_vbo = self._img_n = 0
        self._u_tex_mvp = self._u_tex_rect = self._u_tex_sampler = 0

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
        self._mesh_cache.clear()   # {(path, lod): ...}
        self._inst_cache.clear()   # {(path, lod): ...}
        for defn in definitions:
            self._upload_tile(defn)
        self.doneCurrent()
        self.update()

    def set_pan_speed(self, speed: float) -> None:
        self._pan_speed = speed

    def set_background_color(self, r: float, g: float, b: float,
                             ground: tuple = None, grid: tuple = None) -> None:
        """Set void background, ground plane fill, and grid line colours."""
        self._bg = (r, g, b)
        if ground is not None:
            self._ground_col = ground
        if grid is not None:
            self._grid_col = grid
        if self._ready:
            self.makeCurrent()
            glClearColor(r, g, b, 1.0)
            self.doneCurrent()
            self.update()

    def set_pending_tile(self, definition: Optional[TileDefinition], rotation: int) -> None:
        self._pending_def = definition
        self._pending_rot = rotation
        # Entering palette-tile mode cancels paste ghost mode
        if definition is not None:
            self._paste_buffer = None
        # Recompute hover so the tile pivots around the current cursor position
        mx, my = self._mouse_screen
        self._hover_cell = self._compute_hover_cell(mx, my)
        self.update()

    def set_paste_buffer(self, buf: Optional[list]) -> None:
        """Enter paste-ghost mode. buf is list of (TileDefinition, rel_x, rel_y, rotation, rel_z)."""
        self._paste_buffer = buf
        self.update()

    def refresh(self) -> None:
        self.update()

    def set_ground_image(self, path: str, rect: list) -> None:
        """Load an image from *path* and render it on the ground plane at *rect* (x, y, w, h)."""
        if not self._ready:
            return
        self.makeCurrent()
        if self._tex_id:
            glDeleteTextures([self._tex_id])
            self._tex_id = 0
        img = QImage(path).convertToFormat(QImage.Format_RGBA8888).mirrored(False, True)
        if img.isNull():
            self.doneCurrent()
            return
        ptr = img.bits()
        ptr.setsize(img.byteCount())
        data = np.frombuffer(ptr, dtype=np.uint8).copy()
        self._tex_id = int(glGenTextures(1))
        glBindTexture(GL_TEXTURE_2D, self._tex_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width(), img.height(),
                     0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self._img_rect = list(rect)
        self._rebuild_image_quad()
        self.doneCurrent()
        self.update()

    def clear_ground_image(self) -> None:
        """Remove the ground image texture."""
        if not self._ready or not self._tex_id:
            return
        self.makeCurrent()
        glDeleteTextures([self._tex_id])
        self._tex_id = 0
        if self._img_vao:
            glDeleteVertexArrays(1, [self._img_vao])
            glDeleteBuffers(1, [self._img_vbo])
            self._img_vao = self._img_vbo = self._img_n = 0
        self.doneCurrent()
        self.update()

    def set_ground_image_rect(self, rect: list) -> None:
        """Update the image position/size without reloading the texture (used by scale slider)."""
        if not self._tex_id:
            return
        self._img_rect = list(rect)
        self.makeCurrent()
        self._rebuild_image_quad()
        self.doneCurrent()
        self.update()

    def _rebuild_image_quad(self) -> None:
        """(Re)build the VAO for the ground image quad."""
        if self._img_vao:
            glDeleteVertexArrays(1, [self._img_vao])
            glDeleteBuffers(1, [self._img_vbo])
            self._img_vao = self._img_vbo = self._img_n = 0
        x, y, w, h = self._img_rect
        z = -0.04  # image quad — between ground and grid lines
        verts = np.array([
            x,     y,     z,
            x + w, y,     z,
            x + w, y + h, z,
            x,     y,     z,
            x + w, y + h, z,
            x,     y + h, z,
        ], dtype=np.float32)
        self._img_vao, self._img_vbo, self._img_n = _upload_geometry(verts, 3)

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
        self._instances_dirty = True
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
            self._mesh_prog    = self._build_program(_MESH_VERT,    _MESH_FRAG)
            self._flat_prog    = self._build_program(_FLAT_VERT,    _FLAT_FRAG)
            self._tex_prog     = self._build_program(_TEX_VERT,     _TEX_FRAG)
            self._inst_prog    = self._build_program(_INST_VERT,    _INST_FRAG)
            self._outline_prog = self._build_program(_OUTLINE_VERT, _OUTLINE_FRAG)

            # Uniform locations — mesh (per-draw, used for ghosts)
            p = self._mesh_prog
            self._u_mvp   = glGetUniformLocation(p, b"uMVP")
            self._u_ns    = glGetUniformLocation(p, b"uNormScale")
            self._u_col   = glGetUniformLocation(p, b"uColor")
            self._u_alpha = glGetUniformLocation(p, b"uAlpha")
            self._u_rotz  = glGetUniformLocation(p, b"uRotZ")

            # Uniform locations — outline
            self._u_outline_mvp   = glGetUniformLocation(self._outline_prog, b"uMVP")
            self._u_outline_color = glGetUniformLocation(self._outline_prog, b"uColor")

            # Uniform locations — instanced
            self._u_inst_pv = glGetUniformLocation(self._inst_prog, b"uPV")

            # Uniform locations — flat
            p = self._flat_prog
            self._u_flat_mvp = glGetUniformLocation(p, b"uMVP")
            self._u_flat_col = glGetUniformLocation(p, b"uColor")

            # Uniform locations — textured ground image
            p = self._tex_prog
            self._u_tex_mvp     = glGetUniformLocation(p, b"uMVP")
            self._u_tex_rect    = glGetUniformLocation(p, b"uTexRect")
            self._u_tex_sampler = glGetUniformLocation(p, b"uTex")

            glEnable(GL_DEPTH_TEST)
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)
            glClearColor(*self._bg, 1.0)

            self._build_static_geometry()

            # Scratch VAO for selection highlight quads (updated each frame)
            self._sel_vao = int(glGenVertexArrays(1))
            self._sel_vbo = int(glGenBuffers(1))
            glBindVertexArray(self._sel_vao)
            glBindBuffer(GL_ARRAY_BUFFER, self._sel_vbo)
            placeholder = np.zeros(18, dtype=np.float32)
            glBufferData(GL_ARRAY_BUFFER, placeholder.nbytes, placeholder, GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 12, ctypes.c_void_p(0))
            glBindVertexArray(0)

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

        # Rebuild per-instance GPU data every frame — LOD selection depends on
        # camera distance, which changes whenever the camera moves.
        self._rebuild_instance_buffers()

        glEnable(GL_DEPTH_TEST)   # QPainter may have disabled this in a prior frame
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)

        proj, view = self._get_proj_view()
        pv = proj * view
        pv_arr = np.array(pv.data(), dtype=np.float32)

        # --- Ground plane and grid lines ---
        glUseProgram(self._flat_prog)
        glUniformMatrix4fv(self._u_flat_mvp, 1, GL_FALSE, pv_arr)
        glUniform4f(self._u_flat_col, *self._ground_col, 1.0)
        glBindVertexArray(self._ground_vao)
        glDrawArrays(GL_TRIANGLES, 0, self._ground_n)

        # --- Ground image ---
        if self._tex_id and self._img_n:
            glUseProgram(self._tex_prog)
            glUniformMatrix4fv(self._u_tex_mvp, 1, GL_FALSE, pv_arr)
            glUniform4f(self._u_tex_rect, *self._img_rect)
            glActiveTexture(GL_TEXTURE0)
            glBindTexture(GL_TEXTURE_2D, self._tex_id)
            glUniform1i(self._u_tex_sampler, 0)
            glBindVertexArray(self._img_vao)
            glDrawArrays(GL_TRIANGLES, 0, self._img_n)
            glBindVertexArray(0)
            glUseProgram(self._flat_prog)
            glUniformMatrix4fv(self._u_flat_mvp, 1, GL_FALSE, pv_arr)

        glUniform4f(self._u_flat_col, *self._grid_col, 1.0)
        glLineWidth(1.0)
        glBindVertexArray(self._grid_vao)
        glDrawArrays(GL_LINES, 0, self._grid_n)
        glBindVertexArray(0)

        # --- Placed tiles (instanced — one draw call per unique mesh+LOD) ---
        glUseProgram(self._inst_prog)
        glUniformMatrix4fv(self._u_inst_pv, 1, GL_FALSE, pv_arr)
        for key, count in self._inst_counts.items():
            if count == 0:
                continue
            inst_vao, _inst_vbo, n_verts = self._inst_cache[key]
            glBindVertexArray(inst_vao)
            glDrawArraysInstanced(GL_TRIANGLES, 0, n_verts, count)
        glBindVertexArray(0)

        # --- Selection outline (stencil + back-face extrusion) ---
        # Drawn AFTER all instanced tiles so the depth buffer is fully populated.
        # The outline is correctly occluded by any tile in front of the selected tile.
        # Pass 1: stamp stencil=1 where the selected tile is visible.  Polygon
        #         offset pushes the stencil mesh slightly toward the camera so it
        #         reliably passes the depth test against the already-drawn surface.
        # Pass 2: draw enlarged shell (front-faces culled) only where stencil==0.
        if self._selection:
            glEnable(GL_STENCIL_TEST)
            glUseProgram(self._outline_prog)
            glDepthMask(GL_FALSE)

            # Pass 1 — write stencil, suppress colour
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(-1.0, -1.0)
            glStencilFunc(GL_ALWAYS, 1, 0xFF)
            glStencilOp(GL_KEEP, GL_KEEP, GL_REPLACE)
            glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
            for pt in self._selection:
                self._draw_tile_outline(pt, proj, view, scale=1.0)
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
            glDisable(GL_POLYGON_OFFSET_FILL)

            # Pass 2 — draw outline only where stencil == 0
            glStencilFunc(GL_NOTEQUAL, 1, 0xFF)
            glStencilOp(GL_KEEP, GL_KEEP, GL_KEEP)
            glCullFace(GL_FRONT)
            glUniform4f(self._u_outline_color, 0.0, 0.47, 0.83, 1.0)  # #0078D4
            for pt in self._selection:
                self._draw_tile_outline(pt, proj, view, scale=1.04)
            glCullFace(GL_BACK)

            glDepthMask(GL_TRUE)
            glDisable(GL_STENCIL_TEST)

        # --- Ghost draws (move, paste, placement) — disable culling so semi-transparent
        #     tiles are visible from all angles regardless of winding ---
        glDisable(GL_CULL_FACE)

        # --- Move ghost ---
        if self._move_dragging and self._selection:
            dx, dy = self._move_delta
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glUseProgram(self._mesh_prog)
            for pt in self._selection:
                offsets = self._move_snap_offsets.get(pt)
                if offsets is None:
                    continue
                ox, oy = offsets
                rot = self._move_rotations.get(pt, pt.rotation)
                ghost = PlacedTile(pt.definition, ox + dx, oy + dy, rot, pt.z_offset)
                self._draw_tile(ghost, proj, view, alpha=0.5)
            glDisable(GL_BLEND)

        # --- Paste ghost preview ---
        if self._paste_buffer is not None:
            world = self._ray_to_world(*self._mouse_screen, 0.0)
            if world is not None:
                cx = round(world[0])
                cy = round(world[1])
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                glUseProgram(self._mesh_prog)
                for defn, rel_x, rel_y, rotation, rel_z in self._paste_buffer:
                    gx = cx + rel_x
                    gy = cy + rel_y
                    ghost = PlacedTile(defn, gx, gy, rotation, rel_z)
                    self._draw_tile(ghost, proj, view, alpha=0.5)
                glDisable(GL_BLEND)

        # --- Ghost preview (pending placement) ---
        fx, fy = self._hover_pos
        free_mode = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        if self._pending_def is not None and fx >= -self._pending_def.grid_w:
            igx, igy = int(math.floor(fx)), int(math.floor(fy))
            z_off = self._model.top_z_at(igx, igy) if igx >= 0 else 0.0
            ghost = PlacedTile(self._pending_def, fx, fy, self._pending_rot, z_offset=z_off)
            if free_mode or self._model.can_place(ghost):
                glEnable(GL_BLEND)
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                glUseProgram(self._mesh_prog)
                self._draw_tile(ghost, proj, view, alpha=0.45)
                glDisable(GL_BLEND)

        glEnable(GL_CULL_FACE)

        # --- Rubber-band selection box (native GL, screen-space ortho) ---
        if self._box_start_screen is not None and self._box_end_screen is not None:
            x0, y0 = float(self._box_start_screen[0]), float(self._box_start_screen[1])
            x1, y1 = float(self._box_end_screen[0]),   float(self._box_end_screen[1])
            ortho = QMatrix4x4()
            ortho.ortho(0, max(self.width(), 1), max(self.height(), 1), 0, -1, 1)
            ortho_arr = np.array(ortho.data(), dtype=np.float32)

            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glUseProgram(self._flat_prog)
            glUniformMatrix4fv(self._u_flat_mvp, 1, GL_FALSE, ortho_arr)

            # Filled interior
            fill = np.array([
                x0, y0, 0,  x1, y0, 0,  x1, y1, 0,
                x0, y0, 0,  x1, y1, 0,  x0, y1, 0,
            ], dtype=np.float32)
            glBindVertexArray(self._sel_vao)
            glBindBuffer(GL_ARRAY_BUFFER, self._sel_vbo)
            glBufferData(GL_ARRAY_BUFFER, fill.nbytes, fill, GL_STATIC_DRAW)
            glUniform4f(self._u_flat_col, 0.0, 0.47, 0.83, 0.12)
            glDrawArrays(GL_TRIANGLES, 0, 6)

            # Border
            border = np.array([
                x0, y0, 0,  x1, y0, 0,  x1, y1, 0,  x0, y1, 0,
            ], dtype=np.float32)
            glBufferData(GL_ARRAY_BUFFER, border.nbytes, border, GL_STATIC_DRAW)
            glUniform4f(self._u_flat_col, 0.0, 0.47, 0.83, 0.9)
            glDrawArrays(GL_LINE_LOOP, 0, 4)
            glBindVertexArray(0)

            glDisable(GL_BLEND)
            glEnable(GL_DEPTH_TEST)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_tile(self, pt: PlacedTile, proj: QMatrix4x4, view: QMatrix4x4, alpha: float) -> None:
        defn = pt.definition
        key  = (defn.stl_path, 0)   # ghost draws always use highest available LOD (150³)

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

    def _draw_tile_outline(self, pt: PlacedTile, proj: QMatrix4x4, view: QMatrix4x4,
                           scale: float = 1.04) -> None:
        """Draw a solid-colour back-face shell slightly larger than the tile mesh.

        With GL_CULL_FACE set to GL_FRONT the enlarged back-faces that extend
        beyond the original surface form a clean 3D outline.
        """
        defn = pt.definition
        key  = (defn.stl_path, 0)
        if key not in self._mesh_cache:
            return
        vao, _vbo, n_verts = self._mesh_cache[key]

        ew = float(pt.effective_w) * scale
        eh = float(pt.effective_h) * scale
        gz = float(defn.grid_z)    * scale

        # Shift origin so the enlarged tile stays centred on the original
        gx    = float(pt.grid_x)   - float(pt.effective_w) * (scale - 1) * 0.5
        gy    = float(pt.grid_y)   - float(pt.effective_h) * (scale - 1) * 0.5
        gz_o  = pt.z_offset        - float(defn.grid_z)    * (scale - 1) * 0.5

        model = QMatrix4x4()
        model.translate(gx, gy, gz_o)
        model.scale(ew, eh, gz)
        if pt.rotation != 0:
            model.translate(0.5, 0.5, 0.0)
            model.rotate(float(pt.rotation), 0.0, 0.0, 1.0)
            model.translate(-0.5, -0.5, 0.0)

        mvp_arr = np.array((proj * view * model).data(), dtype=np.float32)
        glUniformMatrix4fv(self._u_outline_mvp, 1, GL_FALSE, mvp_arr)

        glBindVertexArray(vao)
        glDrawArrays(GL_TRIANGLES, 0, n_verts)
        glBindVertexArray(0)

    def _rotate_paste_buffer(self) -> None:
        """Rotate all paste ghosts 90° CCW around their group centroid (R during paste mode)."""
        if not self._paste_buffer:
            return
        new_buf = []
        for defn, rel_x, rel_y, rotation, rel_z in self._paste_buffer:
            # Effective dims at current rotation
            if rotation in (90, 270):
                old_ew = float(defn.grid_h)
                old_eh = float(defn.grid_w)
            else:
                old_ew = float(defn.grid_w)
                old_eh = float(defn.grid_h)
            # Rotate tile centre 90° CCW: (cx, cy) → (-cy, cx), centroid is at origin
            # new_rel_x = -(rel_y + old_eh/2) - new_ew/2  where new_ew = old_eh
            #           = -rel_y - old_eh
            # new_rel_y = (rel_x + old_ew/2) - new_eh/2   where new_eh = old_ew
            #           = rel_x
            new_rel_x = -rel_y - old_eh
            new_rel_y = rel_x
            new_rot = (rotation + 90) % 360
            new_buf.append((defn, new_rel_x, new_rel_y, new_rot, rel_z))
        self._paste_buffer = new_buf
        self.update()

    def _rotate_move_ghosts(self) -> None:
        """Rotate ghost positions 90° CCW around their group centroid (R during drag)."""
        dx, dy = self._move_delta

        # Collect current ghost centres and their effective dims at current rotation
        centers = {}
        dims = {}
        for pt in self._selection:
            offsets = self._move_snap_offsets.get(pt)
            if offsets is None:
                continue
            ox, oy = offsets
            rot = self._move_rotations.get(pt, pt.rotation)
            if rot in (90, 270):
                ew = float(pt.definition.grid_h)
                eh = float(pt.definition.grid_w)
            else:
                ew = float(pt.definition.grid_w)
                eh = float(pt.definition.grid_h)
            gx = ox + dx
            gy = oy + dy
            centers[pt] = (gx + ew / 2.0, gy + eh / 2.0)
            dims[pt] = (ew, eh)

        if not centers:
            return

        # Group centroid
        group_cx = sum(c[0] for c in centers.values()) / len(centers)
        group_cy = sum(c[1] for c in centers.values()) / len(centers)

        new_snap = {}
        new_rots = {}
        for pt in self._selection:
            if pt not in centers:
                continue
            cur_cx, cur_cy = centers[pt]
            old_ew, old_eh = dims[pt]
            new_ew, new_eh = old_eh, old_ew   # swap after 90°
            new_rot = (self._move_rotations.get(pt, pt.rotation) + 90) % 360

            # Rotate centre 90° CCW around group centroid
            rx = cur_cx - group_cx
            ry = cur_cy - group_cy
            new_cx = group_cx - ry
            new_cy = group_cy + rx

            # Back out the current delta to get the new snap offset
            new_snap[pt] = (new_cx - new_ew / 2.0 - dx,
                            new_cy - new_eh / 2.0 - dy)
            new_rots[pt] = new_rot

        self._move_snap_offsets = new_snap
        self._move_rotations = new_rots
        self.update()

    def _draw_flat_rect(self, x: float, y: float, w: float, h: float,
                        z: float, rgba: tuple) -> None:
        """Draw a flat colored quad using the flat shader (reuses scratch VAO)."""
        verts = np.array([
            x,     y,     z,
            x + w, y,     z,
            x + w, y + h, z,
            x,     y,     z,
            x + w, y + h, z,
            x,     y + h, z,
        ], dtype=np.float32)
        glBindVertexArray(self._sel_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self._sel_vbo)
        glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
        glUniform4f(self._u_flat_col, *rgba)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindVertexArray(0)

    # ------------------------------------------------------------------
    # GPU resource management
    # ------------------------------------------------------------------

    def _upload_tile(self, defn: TileDefinition) -> None:
        """Upload VAOs for all LOD levels of defn."""
        for lod, tris in enumerate(defn.lod_triangles):
            if tris is None or len(tris) == 0:
                continue
            vdata = _build_vdata(tris)
            if len(vdata) == 0:
                continue
            self._upload_tile_lod(defn.stl_path, lod, vdata)

    def _upload_tile_lod(self, path: str, lod: int, vdata: np.ndarray) -> None:
        """Upload one LOD level's VBO data and create both ghost and instanced VAOs."""
        # Ghost VAO (attribs 0, 1 — used by _draw_tile for ghost/preview draws)
        ghost_vao, mesh_vbo, n_verts = _upload_geometry(vdata, 6)
        self._mesh_cache[(path, lod)] = (ghost_vao, mesh_vbo, n_verts)

        # Instanced VAO (attribs 0-5, per-instance divisor=1 on attribs 2-5)
        INST_STRIDE = 11 * 4   # 11 floats × 4 bytes = 44 bytes
        inst_vao = int(glGenVertexArrays(1))
        glBindVertexArray(inst_vao)

        glBindBuffer(GL_ARRAY_BUFFER, mesh_vbo)
        mesh_stride = 6 * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, mesh_stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, mesh_stride, ctypes.c_void_p(12))

        inst_vbo = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, inst_vbo)
        glEnableVertexAttribArray(2)
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, INST_STRIDE, ctypes.c_void_p(0))
        glVertexAttribDivisor(2, 1)
        glEnableVertexAttribArray(3)
        glVertexAttribPointer(3, 1, GL_FLOAT, GL_FALSE, INST_STRIDE, ctypes.c_void_p(12))
        glVertexAttribDivisor(3, 1)
        glEnableVertexAttribArray(4)
        glVertexAttribPointer(4, 3, GL_FLOAT, GL_FALSE, INST_STRIDE, ctypes.c_void_p(16))
        glVertexAttribDivisor(4, 1)
        glEnableVertexAttribArray(5)
        glVertexAttribPointer(5, 4, GL_FLOAT, GL_FALSE, INST_STRIDE, ctypes.c_void_p(28))
        glVertexAttribDivisor(5, 1)
        glBindVertexArray(0)

        self._inst_cache[(path, lod)] = (inst_vao, inst_vbo, n_verts)

    # LOD distance thresholds (eye-to-tile distance in grid cells)
    _LOD_DISTS = (10.0, 80.0)   # <10 → LOD0 (150³), 10–80 → LOD1 (85³), ≥80 → LOD2 (25³)

    def _lod_for_dist(self, dist: float) -> int:
        for lod, threshold in enumerate(self._LOD_DISTS):
            if dist < threshold:
                return lod
        return len(self._LOD_DISTS)

    def _rebuild_instance_buffers(self) -> None:
        """Group placed tiles by (mesh, lod) and upload per-instance data to the GPU.

        Frustum culling is done with a single batched numpy operation across all
        placed tiles — one Python loop collects AABB data, then all six plane tests
        run in one vectorised pass, producing a boolean visibility mask.  Only
        visible tiles enter the instance groups.
        """
        proj, view = self._get_proj_view()
        pv = proj * view

        eye = self._eye_pos()
        ex, ey, ez = eye.x(), eye.y(), eye.z()

        # Gribb-Hartmann frustum plane extraction from the PV matrix.
        # Qt data() is column-major → reshape(4,4) yields pv_np = M^T.
        # Rows of M == columns of pv_np.
        pv_np = np.array(pv.data(), dtype=np.float64).reshape(4, 4)
        c0, c1, c2, c3 = pv_np[:, 0], pv_np[:, 1], pv_np[:, 2], pv_np[:, 3]
        planes    = np.array([c3+c0, c3-c0, c3+c1, c3-c1, c3+c2, c3-c2])  # (6,4)
        plane_abc = planes[:, :3]   # (6, 3)
        plane_d   = planes[:,  3]   # (6,)

        all_placed = list(self._model.all_placed())
        n = len(all_placed)

        self._inst_counts = {}
        if n == 0:
            return

        # --- Single Python loop: collect per-tile scalars into flat arrays ---
        t_gx  = np.empty(n, np.float64)
        t_gy  = np.empty(n, np.float64)
        t_gzo = np.empty(n, np.float64)
        t_ew  = np.empty(n, np.float64)
        t_eh  = np.empty(n, np.float64)
        t_gz  = np.empty(n, np.float64)
        for i, pt in enumerate(all_placed):
            t_gx[i]  = pt.grid_x
            t_gy[i]  = pt.grid_y
            t_gzo[i] = pt.z_offset
            t_ew[i]  = pt.effective_w
            t_eh[i]  = pt.effective_h
            t_gz[i]  = pt.definition.grid_z

        # --- Vectorised frustum cull ---
        # AABB: min=(gx, gy, gz_off), max=(gx+ew, gy+eh, gz_off+gz)
        aabb_min = np.stack([t_gx,          t_gy,          t_gzo         ], axis=1)  # (N,3)
        aabb_max = np.stack([t_gx + t_ew,   t_gy + t_eh,   t_gzo + t_gz  ], axis=1)  # (N,3)

        # For each plane choose the p-vertex (corner maximising signed distance).
        # plane_abc[:,None,:] is (6,1,3), aabb_* are (1,N,3) via broadcasting.
        p_verts = np.where(
            plane_abc[:, np.newaxis, :] >= 0,
            aabb_max[np.newaxis, :, :],
            aabb_min[np.newaxis, :, :],
        )  # (6, N, 3)
        signed_dists = (p_verts * plane_abc[:, np.newaxis, :]).sum(axis=2) \
                       + plane_d[:, np.newaxis]           # (6, N)
        visible_mask = np.all(signed_dists >= 0.0, axis=0)   # (N,)  True = inside frustum

        # --- Vectorised LOD distance ---
        cx   = t_gx + t_ew * 0.5
        cy   = t_gy + t_eh * 0.5
        cz   = t_gzo + t_gz * 0.5
        dist = np.sqrt((cx - ex)**2 + (cy - ey)**2 + (cz - ez)**2)  # (N,)

        # --- Group visible tiles by (path, lod) ---
        groups: Dict[Tuple[str, int], list] = {}
        for i in np.where(visible_mask)[0]:
            pt   = all_placed[i]
            path = pt.definition.stl_path
            lod  = self._lod_for_dist(float(dist[i]))

            key = (path, lod)
            while lod > 0 and key not in self._inst_cache:
                lod -= 1
                key = (path, lod)
            if key not in self._inst_cache:
                continue

            if key not in groups:
                groups[key] = []
            col = pt.definition.color
            groups[key].append((
                float(t_gx[i]), float(t_gy[i]), float(t_gzo[i]),
                math.radians(pt.rotation),
                float(t_ew[i]), float(t_eh[i]), float(t_gz[i]),
                col.redF(), col.greenF(), col.blueF(), 1.0,
            ))

        # Upload each group and record instance counts for the draw loop
        self._inst_counts: Dict[Tuple[str, int], int] = {}
        for key, instances in groups.items():
            inst_vao, inst_vbo, _n = self._inst_cache[key]
            data = np.array(instances, dtype=np.float32)
            glBindVertexArray(inst_vao)
            glBindBuffer(GL_ARRAY_BUFFER, inst_vbo)
            glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
            glBindVertexArray(0)
            self._inst_counts[key] = len(instances)

    def _build_static_geometry(self) -> None:
        """Build ground plane and grid line geometry."""
        cols = self._model.GRID_COLS
        rows = self._model.GRID_ROWS
        z = -0.06  # ground plane — well below tile floor

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
        gz = -0.02  # grid lines — above image, below tiles
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

    def _tile_verts_in_box(self, pt: 'PlacedTile', pv_np: np.ndarray,
                           rx: tuple, ry: tuple, sw: int, sh: int) -> bool:
        """Return True if the tile's screen-space bounding box overlaps the selection box rx×ry.

        Projects the 8 corners of the tile's axis-aligned bounding box (O(8) per tile)
        instead of all mesh vertices — fast enough for scenes with thousands of tiles.
        The overlap test is conservative: tiles whose projected AABB touches the selection
        rect are included even if the mesh itself doesn't reach that corner.
        """
        ew = float(pt.effective_w)
        eh = float(pt.effective_h)
        gz = float(pt.definition.grid_z)

        model_mat = QMatrix4x4()
        model_mat.translate(float(pt.grid_x), float(pt.grid_y), pt.z_offset)
        model_mat.scale(ew, eh, gz)
        if pt.rotation != 0:
            model_mat.translate(0.5, 0.5, 0.0)
            model_mat.rotate(float(pt.rotation), 0.0, 0.0, 1.0)
            model_mat.translate(-0.5, -0.5, 0.0)

        model_np = np.array(model_mat.data(), dtype=np.float32).reshape(4, 4)
        mvp_np   = model_np @ pv_np

        # 8 corners of the unit cube [0,1]³ in tile local space
        corners = np.array([
            [x, y, z, 1.0]
            for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)
        ], dtype=np.float32)                                 # (8, 4)
        clip = corners @ mvp_np                              # (8, 4)

        w_vals  = clip[:, 3]
        visible = w_vals > 1e-6
        if not np.any(visible):
            return False

        safe_w  = np.where(visible, w_vals, 1.0)
        ndc_x   = clip[:, 0] / safe_w
        ndc_y   = clip[:, 1] / safe_w
        sx_all  = (ndc_x * 0.5 + 0.5) * sw
        sy_all  = (1.0 - (ndc_y * 0.5 + 0.5)) * sh

        vis_sx  = sx_all[visible]
        vis_sy  = sy_all[visible]

        # Overlap: projected AABB of tile corners vs selection rect
        return (vis_sx.max() >= rx[0] and vis_sx.min() <= rx[1] and
                vis_sy.max() >= ry[0] and vis_sy.min() <= ry[1])

    def _pick_tile(self, sx: int, sy: int) -> Optional['PlacedTile']:
        """Return the front-most PlacedTile whose mesh the screen ray hits."""
        w, h = max(self.width(), 1), max(self.height(), 1)
        proj, view = self._get_proj_view()
        inv_pv, ok = (proj * view).inverted()
        if not ok:
            return None

        ndx = (2.0 * sx / w) - 1.0
        ndy = 1.0 - (2.0 * sy / h)
        near4 = inv_pv * QVector4D(ndx, ndy, -1.0, 1.0)
        far4  = inv_pv * QVector4D(ndx, ndy,  1.0, 1.0)
        near = np.array([near4.x()/near4.w(), near4.y()/near4.w(), near4.z()/near4.w()])
        far  = np.array([far4.x()/far4.w(),   far4.y()/far4.w(),   far4.z()/far4.w()])
        ray_dir = far - near
        ray_len = np.linalg.norm(ray_dir)
        if ray_len < 1e-10:
            return None
        ray_dir /= ray_len

        best_t    = np.inf
        best_tile = None
        _zero = np.zeros(3)
        _one  = np.ones(3)

        for pt in self._model.all_placed():
            defn = pt.definition
            if defn.view_triangles is None or len(defn.view_triangles) == 0:
                continue

            ew = float(pt.effective_w)
            eh = float(pt.effective_h)
            gz = float(defn.grid_z)

            # Reconstruct the same model matrix used in _draw_tile
            model_mat = QMatrix4x4()
            model_mat.translate(float(pt.grid_x), float(pt.grid_y), pt.z_offset)
            model_mat.scale(ew, eh, gz)
            if pt.rotation != 0:
                model_mat.translate(0.5, 0.5, 0.0)
                model_mat.rotate(float(pt.rotation), 0.0, 0.0, 1.0)
                model_mat.translate(-0.5, -0.5, 0.0)

            inv_model, ok = model_mat.inverted()
            if not ok:
                continue

            # Transform ray endpoints to local [0,1]³ space
            def _xform(v):
                q = inv_model * QVector4D(v[0], v[1], v[2], 1.0)
                return np.array([q.x()/q.w(), q.y()/q.w(), q.z()/q.w()])

            lo = _xform(near)
            ld = _xform(far) - lo
            ld_len = np.linalg.norm(ld)
            if ld_len < 1e-10:
                continue
            ld /= ld_len

            # Fast AABB reject before triangle test
            if not _ray_aabb(lo, ld, _zero, _one):
                continue

            t_local = _ray_triangles_min_t(lo, ld, defn.view_triangles)
            if t_local is None:
                continue

            # Convert local hit to world distance for depth sorting
            hit_local = lo + ld * t_local
            q = model_mat * QVector4D(hit_local[0], hit_local[1], hit_local[2], 1.0)
            hit_world = np.array([q.x()/q.w(), q.y()/q.w(), q.z()/q.w()])
            world_t = float(np.dot(hit_world - near, ray_dir))

            if world_t < best_t:
                best_t    = world_t
                best_tile = pt

        return best_tile

    def _compute_hover_cell(self, mx: int, my: int) -> Tuple[int, int]:
        """Return the snapped grid origin for the pending tile centered on the cursor."""
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

    def _compute_free_pos(self, mx: int, my: int) -> Tuple[float, float]:
        """Return continuous world position for the pending tile centered on the cursor (Ctrl mode)."""
        world = self._ray_to_world(mx, my, 0.0)
        if world is None:
            return -1.0, -1.0
        hx, hy = world
        if self._pending_def is None:
            return hx, hy
        if self._pending_rot in (90, 270):
            ew = float(self._pending_def.grid_h)
            eh = float(self._pending_def.grid_w)
        else:
            ew = float(self._pending_def.grid_w)
            eh = float(self._pending_def.grid_h)
        return hx - ew / 2.0, hy - eh / 2.0

    # ------------------------------------------------------------------
    # Mouse / keyboard events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._last_mouse = event.pos()
        self._drag_button = event.button()

        if event.button() == Qt.LeftButton:
            if self._tex_id and (event.modifiers() & Qt.AltModifier):
                # Start image drag
                world = self._ray_to_world(event.x(), event.y(), 0.0)
                if world:
                    self._img_dragging = True
                    self._img_drag_start_world = world
                    self._img_drag_start_rect = list(self._img_rect)
            elif self._paste_buffer is not None:
                # Paste mode — place the ghost group at the cursor position
                world = self._ray_to_world(event.x(), event.y(), 0.0)
                if world is None:
                    world = (self._model.GRID_COLS / 2.0, self._model.GRID_ROWS / 2.0)
                cx = round(world[0])
                cy = round(world[1])
                self.paste_place_requested.emit(float(cx), float(cy))
            elif self._pending_def is None:
                # Selection mode — test against actual mesh geometry
                tile = self._pick_tile(event.x(), event.y())
                shift = bool(event.modifiers() & Qt.ShiftModifier)
                if tile is not None:
                    if shift:
                        if tile in self._selection:
                            self._selection.discard(tile)
                        else:
                            self._selection.add(tile)
                    else:
                        if tile not in self._selection:
                            self._selection = {tile}
                    # Prime for potential move drag
                    world = self._ray_to_world(event.x(), event.y(), 0.0)
                    if world and self._selection:
                        self._move_world_start = world
                        self._move_snap_offsets = {
                            pt: (int(math.floor(pt.grid_x)), int(math.floor(pt.grid_y)))
                            for pt in self._selection
                        }
                        self._move_rotations = {}
                else:
                    # Empty cell → start rubber-band
                    if not shift:
                        self._selection.clear()
                    self._box_start_screen = (event.x(), event.y())
                    self._box_end_screen   = (event.x(), event.y())
                self.update()
            else:
                fx, fy = self._hover_pos
                if fx >= -self._pending_def.grid_w if self._pending_def else fx >= 0:
                    self.tile_place_requested.emit(fx, fy)
        elif event.button() == Qt.MiddleButton:
            self._mid_press = event.pos()
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
        elif self._img_dragging and self._img_drag_start_world is not None:
            world = self._ray_to_world(event.x(), event.y(), 0.0)
            if world:
                dx = world[0] - self._img_drag_start_world[0]
                dy = world[1] - self._img_drag_start_world[1]
                self._img_rect[0] = self._img_drag_start_rect[0] + dx
                self._img_rect[1] = self._img_drag_start_rect[1] + dy
                self.makeCurrent()
                self._rebuild_image_quad()
                self.doneCurrent()
                self.ground_image_rect_changed.emit(list(self._img_rect))
                self.update()
        elif self._drag_button == Qt.LeftButton and self._pending_def is None:
            if self._box_start_screen is not None:
                # Extend rubber-band selection box
                self._box_end_screen = (event.x(), event.y())
                self.update()
            elif self._move_world_start is not None:
                world = self._ray_to_world(event.x(), event.y(), 0.0)
                if world:
                    if not self._move_dragging:
                        # Use world-space distance from press point as threshold
                        wdx = world[0] - self._move_world_start[0]
                        wdy = world[1] - self._move_world_start[1]
                        if wdx * wdx + wdy * wdy > 0.09:  # ~0.3 cells
                            self._move_dragging = True
                    if self._move_dragging:
                        free = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
                        raw_dx = world[0] - self._move_world_start[0]
                        raw_dy = world[1] - self._move_world_start[1]
                        if free:
                            self._move_delta = (raw_dx, raw_dy)
                        else:
                            self._move_delta = (round(raw_dx), round(raw_dy))
                        self.update()
        else:
            # Update hover ghost
            self._mouse_screen = (event.x(), event.y())
            free_mode = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
            if free_mode:
                fx, fy = self._compute_free_pos(event.x(), event.y())
                self._hover_pos = (fx, fy)
                new_cell = (int(math.floor(fx)), int(math.floor(fy)))
            else:
                new_cell = self._compute_hover_cell(event.x(), event.y())
                self._hover_pos = (float(new_cell[0]), float(new_cell[1]))
            if new_cell != self._hover_cell or free_mode or self._paste_buffer is not None:
                self._hover_cell = new_cell
                self.hover_cell_changed.emit(*new_cell)
                self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._img_dragging:
            self._img_dragging = False
            self._img_drag_start_world = None
            self._img_drag_start_rect = None
        elif event.button() == Qt.LeftButton and self._pending_def is None:
            if self._move_dragging and (self._move_delta != (0.0, 0.0) or self._move_rotations):
                # Commit move (position change, rotation change, or both)
                free = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
                dx, dy = self._move_delta
                moves = []
                for pt in self._selection:
                    offsets = self._move_snap_offsets.get(pt)
                    if offsets is None:
                        continue
                    ox, oy = offsets
                    rot = self._move_rotations.get(pt, pt.rotation)
                    if free:
                        moves.append((pt, ox + dx, oy + dy, rot))
                    else:
                        moves.append((pt, ox + int(dx), oy + int(dy), rot))
                if moves:
                    self.tiles_move_requested.emit(moves)
            elif self._box_start_screen is not None:
                # Finalise rubber-band box select — tile selected if any mesh vertex inside box
                x0, y0 = self._box_start_screen
                x1, y1 = event.x(), event.y()
                rx = (min(x0, x1), max(x0, x1))
                ry = (min(y0, y1), max(y0, y1))
                proj, view = self._get_proj_view()
                sw, sh = max(self.width(), 1), max(self.height(), 1)
                # pv_np: Qt column-major → numpy gives (PV)^T, used as h @ pv_np
                pv_np = np.array((proj * view).data(), dtype=np.float32).reshape(4, 4)
                for pt in self._model.all_placed():
                    if self._tile_verts_in_box(pt, pv_np, rx, ry, sw, sh):
                        self._selection.add(pt)
            # Reset move/box state
            self._box_start_screen = None
            self._box_end_screen   = None
            self._move_world_start = None
            self._move_snap_offsets.clear()
            self._move_rotations.clear()
            self._move_dragging = False
            self._move_delta    = (0.0, 0.0)
            self.update()
        # Short middle-click (no pan) = pick up tile
        if event.button() == Qt.MiddleButton and hasattr(self, '_mid_press'):
            d = event.pos() - self._mid_press
            if abs(d.x()) < 5 and abs(d.y()) < 5:
                tile = self._pick_tile(event.x(), event.y())
                if tile is not None:
                    self.tile_pickup_requested.emit(tile)
            del self._mid_press
        # Short right-click (no drag) = remove tile
        if event.button() == Qt.RightButton and hasattr(self, '_drag_start'):
            d = event.pos() - self._drag_start
            if abs(d.x()) < 5 and abs(d.y()) < 5:
                tile = self._pick_tile(event.x(), event.y())
                if tile is not None:
                    self.tile_remove_requested.emit(tile)
            del self._drag_start
        self._drag_button = None
        self._last_mouse  = None

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        self._distance = max(2.0, min(200.0, self._distance * factor))
        self.update()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            if self._paste_buffer is not None:
                self._paste_buffer = None
                self.update()
                return
            self._selection.clear()
            self.deselect_requested.emit()
        elif key == Qt.Key_R:
            if self._paste_buffer is not None:
                self._rotate_paste_buffer()
            elif self._move_dragging and self._selection:
                self._rotate_move_ghosts()
            elif self._selection and self._pending_def is None:
                self.selection_rotate_requested.emit()
            else:
                self.rotate_requested.emit()
        elif key == Qt.Key_Delete:
            mx, my = self._mouse_screen
            tile = self._pick_tile(mx, my)
            if tile is not None:
                self.tile_remove_requested.emit(tile)
        elif key == Qt.Key_Home:
            self._reset_camera()
        elif key == Qt.Key_Control:
            mx, my = self._mouse_screen
            fx, fy = self._compute_free_pos(mx, my)
            self._hover_pos = (fx, fy)
            self.update()
        elif key in (Qt.Key_W, Qt.Key_A, Qt.Key_S, Qt.Key_D):
            if not event.isAutoRepeat():
                self._pan_keys.add(key)
                if not self._pan_timer.isActive():
                    self._pan_timer.start()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() in (Qt.Key_W, Qt.Key_A, Qt.Key_S, Qt.Key_D):
            if not event.isAutoRepeat():
                self._pan_keys.discard(event.key())
                if not self._pan_keys:
                    self._pan_timer.stop()
        elif event.key() == Qt.Key_Control:
            # Switch ghost back to snapped mode immediately
            mx, my = self._mouse_screen
            cell = self._compute_hover_cell(mx, my)
            self._hover_pos = (float(cell[0]), float(cell[1]))
            self._hover_cell = cell
            self.update()
        else:
            super().keyReleaseEvent(event)

    def _on_pan_tick(self) -> None:
        """Called at ~60 fps while any WASD key is held; pans the camera target."""
        az      = math.radians(self._azimuth)
        speed   = self._distance * self._pan_speed
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
        self.update()

    # ------------------------------------------------------------------
    # Shader compilation
    # ------------------------------------------------------------------

    def _build_program(self, vert_src: str, frag_src: str) -> int:
        return _build_program_fn(vert_src, frag_src)

    @staticmethod
    def _compile(src: str, kind: int) -> int:
        return _compile_fn(src, kind)
