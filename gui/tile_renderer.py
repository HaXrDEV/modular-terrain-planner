"""
Offscreen OpenGL 3.3 renderer that converts STL mesh data into cached QPixmaps.
Falls back gracefully (returns None) if PyOpenGL is unavailable or the GL
context cannot be created.
"""
import ctypes
import math
from typing import Dict, Optional, Tuple

import numpy as np
from PyQt5.QtCore import QSize
from PyQt5.QtGui import (
    QMatrix4x4,
    QOffscreenSurface,
    QOpenGLContext,
    QOpenGLFramebufferObject,
    QOpenGLFramebufferObjectFormat,
    QPixmap,
    QSurfaceFormat,
    QVector3D,
)

try:
    from OpenGL.GL import (
        GL_ARRAY_BUFFER,
        GL_COLOR_BUFFER_BIT,
        GL_COMPILE_STATUS,
        GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST,
        GL_FALSE,
        GL_FLOAT,
        GL_FRAGMENT_SHADER,
        GL_LINK_STATUS,
        GL_STATIC_DRAW,
        GL_TRIANGLES,
        GL_VERTEX_SHADER,
        glAttachShader,
        glBindBuffer,
        glBindVertexArray,
        glBufferData,
        glClear,
        glClearColor,
        glCompileShader,
        glCreateProgram,
        glCreateShader,
        glDeleteBuffers,
        glDeleteShader,
        glDeleteVertexArrays,
        glDrawArrays,
        glEnable,
        glEnableVertexAttribArray,
        glGenBuffers,
        glGenVertexArrays,
        glGetProgramInfoLog,
        glGetProgramiv,
        glGetShaderInfoLog,
        glGetShaderiv,
        glGetUniformLocation,
        glLinkProgram,
        glShaderSource,
        glUniform3f,
        glUniformMatrix4fv,
        glUseProgram,
        glVertexAttribPointer,
        glViewport,
    )
    _GL_OK = True
except ImportError:
    _GL_OK = False

from models.tile_definition import TileDefinition

# Offscreen render resolution: pixels per grid cell.
# Higher = crisper at max zoom; lower = faster load.
RENDER_CELL_PX = 256

# ---------------------------------------------------------------------------
# GLSL shaders
# ---------------------------------------------------------------------------

_VERT = """\
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNorm;
uniform mat4 uMVP;
out vec3 vNorm;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vNorm = aNorm;
}
"""

_FRAG = """\
#version 330 core
in vec3 vNorm;
uniform vec3 uColor;
out vec4 FragColor;
void main() {
    vec3 n = normalize(vNorm);
    // Three-point flat shading
    float key  = max(dot(n, normalize(vec3(-0.4, -0.6, 1.0))), 0.0) * 0.65;
    float fill = max(dot(n, normalize(vec3( 1.0,  0.5, 0.5))), 0.0) * 0.20;
    float rim  = max(dot(n, normalize(vec3( 0.3,  1.0,-0.3))), 0.0) * 0.10;
    float i = clamp(0.25 + key + fill + rim, 0.0, 1.0);
    FragColor = vec4(uColor * i, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rotate_norm_3d(nx: float, ny: float, nz: float, rotation: int):
    """Z-axis rotation of normalised (nx, ny) around (0.5, 0.5); nz unchanged."""
    cx, cy = nx - 0.5, ny - 0.5
    if rotation == 0:   return nx, ny, nz
    if rotation == 90:  return 0.5 - cy, 0.5 + cx, nz
    if rotation == 180: return 1.0 - nx, 1.0 - ny, nz
    if rotation == 270: return 0.5 + cy, 0.5 - cx, nz
    return nx, ny, nz


def _build_vdata(triangles) -> np.ndarray:
    """Build interleaved (pos xyz, norm xyz) float32 array with flat normals."""
    rows: list = []
    for tri in triangles:
        p0, p1, p2 = tri
        ax = p1[0] - p0[0]; ay = p1[1] - p0[1]; az = p1[2] - p0[2]
        bx = p2[0] - p0[0]; by = p2[1] - p0[1]; bz = p2[2] - p0[2]
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        m = math.sqrt(nx * nx + ny * ny + nz * nz)
        if m < 1e-12:
            nx = ny = 0.0; nz = 1.0
        else:
            nx /= m; ny /= m; nz /= m
        for v in (p0, p1, p2):
            rows += [float(v[0]), float(v[1]), float(v[2]), nx, ny, nz]
    return np.array(rows, dtype=np.float32)


# ---------------------------------------------------------------------------
# TileRenderer
# ---------------------------------------------------------------------------

class TileRenderer:
    """Singleton offscreen OpenGL renderer for STL tile preview pixmaps."""

    _instance: Optional["TileRenderer"] = None

    @classmethod
    def instance(cls) -> Optional["TileRenderer"]:
        """Return the shared renderer, or None if OpenGL is unavailable."""
        if not _GL_OK:
            return None
        if cls._instance is None:
            try:
                cls._instance = TileRenderer()
            except Exception as exc:
                print(f"[TileRenderer] Initialisation failed: {exc}")
                return None
        return cls._instance

    def __init__(self) -> None:
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setAlphaBufferSize(8)

        self._surface = QOffscreenSurface()
        self._surface.setFormat(fmt)
        self._surface.create()
        if not self._surface.isValid():
            raise RuntimeError("QOffscreenSurface is not valid")

        self._ctx = QOpenGLContext()
        self._ctx.setFormat(fmt)
        if not self._ctx.create():
            raise RuntimeError("Failed to create OpenGL 3.3 Core context")

        self._ctx.makeCurrent(self._surface)
        self._prog = self._build_program()
        self._ctx.doneCurrent()

        # Cache: (stl_path, rotation) → QPixmap
        self._cache: Dict[Tuple[str, int], Optional[QPixmap]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pixmap(self, defn: TileDefinition, rotation: int) -> Optional[QPixmap]:
        """Return a cached pixmap for this tile + rotation, rendering if needed."""
        key = (defn.stl_path, rotation)
        if key not in self._cache:
            self._cache[key] = self._render(defn, rotation)
        return self._cache[key]

    def invalidate(self) -> None:
        """Clear the pixmap cache (call after loading a new STL folder)."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self, defn: TileDefinition, rotation: int) -> Optional[QPixmap]:
        if not defn.view_triangles:
            return None

        rotated = [
            [_rotate_norm_3d(v[0], v[1], v[2], rotation) for v in tri]
            for tri in defn.view_triangles
        ]
        vdata = _build_vdata(rotated)
        n_verts = len(vdata) // 6
        if n_verts == 0:
            return None

        w = defn.grid_w * RENDER_CELL_PX
        h = defn.grid_h * RENDER_CELL_PX

        self._ctx.makeCurrent(self._surface)
        try:
            return self._draw(defn, vdata, n_verts, w, h)
        except Exception as exc:
            print(f"[TileRenderer] Render error for '{defn.name}': {exc}")
            return None
        finally:
            self._ctx.doneCurrent()

    def _draw(self, defn, vdata, n_verts, w, h) -> Optional[QPixmap]:
        # --- FBO ---
        fbo_fmt = QOpenGLFramebufferObjectFormat()
        fbo_fmt.setAttachment(QOpenGLFramebufferObject.CombinedDepthStencil)
        fbo = QOpenGLFramebufferObject(QSize(w, h), fbo_fmt)
        if not fbo.bind():
            return None

        glViewport(0, 0, w, h)
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.0, 0.0, 0.0, 0.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # --- Upload geometry ---
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)

        stride = 6 * 4  # 6 floats × 4 bytes
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))

        # --- MVP ---
        proj = QMatrix4x4()
        proj.perspective(38.0, w / h, 0.01, 20.0)
        view = QMatrix4x4()
        view.lookAt(
            QVector3D(0.5,  -0.1, 1.8),   # eye: above and slightly in front
            QVector3D(0.5,   0.5, 0.15),  # target: centre of tile
            QVector3D(0.0,   0.0, 1.0),   # up: Z-axis
        )
        mvp = np.array((proj * view).data(), dtype=np.float32)

        # --- Draw ---
        glUseProgram(self._prog)
        glUniformMatrix4fv(glGetUniformLocation(self._prog, b"uMVP"), 1, GL_FALSE, mvp)
        glUniform3f(
            glGetUniformLocation(self._prog, b"uColor"),
            defn.color.redF(), defn.color.greenF(), defn.color.blueF(),
        )
        glDrawArrays(GL_TRIANGLES, 0, n_verts)

        # --- Read back ---
        fbo.release()
        image = fbo.toImage()

        # Cleanup
        glDeleteBuffers(1, [vbo])
        glDeleteVertexArrays(1, [vao])

        return QPixmap.fromImage(image) if image and not image.isNull() else None

    # ------------------------------------------------------------------
    # Shader compilation
    # ------------------------------------------------------------------

    def _build_program(self) -> int:
        vs = self._compile(_VERT, GL_VERTEX_SHADER)
        fs = self._compile(_FRAG, GL_FRAGMENT_SHADER)
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
