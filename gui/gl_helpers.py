"""
Shared OpenGL helper functions and shader source strings.

Used by both GLGridView (grid scene) and TilePreviewWidget (palette preview)
so the shader code and geometry-building logic are not duplicated.
"""
import ctypes
from typing import Tuple

import numpy as np

try:
    from OpenGL.GL import (
        GL_ARRAY_BUFFER, GL_COMPILE_STATUS, GL_FALSE, GL_FLOAT,
        GL_FRAGMENT_SHADER, GL_LINK_STATUS, GL_STATIC_DRAW, GL_VERTEX_SHADER,
        glAttachShader, glBindBuffer, glBindVertexArray, glBufferData,
        glCompileShader, glCreateProgram, glCreateShader, glDeleteShader,
        glEnableVertexAttribArray, glGenBuffers, glGenVertexArrays,
        glGetProgramInfoLog, glGetProgramiv, glGetShaderInfoLog,
        glGetShaderiv, glLinkProgram, glShaderSource, glVertexAttribPointer,
    )
    _GL_OK = True
except ImportError:
    _GL_OK = False

# ---------------------------------------------------------------------------
# GLSL shader source
# ---------------------------------------------------------------------------

MESH_VERT = """\
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNorm;
uniform mat4 uMVP;
uniform vec3 uNormScale;
uniform float uRotZ;
out vec3 vNorm;
void main() {
    gl_Position = uMVP * vec4(aPos, 1.0);
    vec3 ns = aNorm * uNormScale;
    float c = cos(uRotZ), s = sin(uRotZ);
    vNorm = normalize(vec3(c*ns.x - s*ns.y, s*ns.x + c*ns.y, ns.z));
}
"""

MESH_FRAG = """\
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

# ---------------------------------------------------------------------------
# CPU-side geometry helpers
# ---------------------------------------------------------------------------

def build_vdata(triangles: np.ndarray) -> np.ndarray:
    """
    Build interleaved (pos xyz, norm xyz) float32 VBO data from a (N, 3, 3) array.

    Computes flat per-face normals via cross product and returns a flat
    (N*3*6,) float32 array. Rotation is handled at draw time via the model
    matrix and the uRotZ shader uniform.
    """
    tris = triangles  # (N, 3, 3) — no copy needed, read-only

    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    norms = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(norms, axis=1, keepdims=True)
    degen = (lengths < 1e-12).squeeze(axis=1)
    lengths = np.where(lengths < 1e-12, 1.0, lengths)
    norms /= lengths
    norms[degen] = [0.0, 0.0, 1.0]

    norms_exp = np.repeat(norms[:, np.newaxis, :], 3, axis=1)
    combined = np.concatenate([tris, norms_exp], axis=2)  # (N, 3, 6)
    return combined.reshape(-1).astype(np.float32)


def upload_geometry(vdata: np.ndarray, n_attribs: int = 6) -> Tuple[int, int, int]:
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


def compile_shader(src: str, kind: int) -> int:
    """Compile a single GLSL shader stage. Raises RuntimeError on failure."""
    s = glCreateShader(kind)
    glShaderSource(s, src)
    glCompileShader(s)
    if not glGetShaderiv(s, GL_COMPILE_STATUS):
        err = glGetShaderInfoLog(s)
        raise RuntimeError(f"Shader compile: {err}")
    return s


def build_program(vert_src: str, frag_src: str) -> int:
    """Compile and link a GLSL program. Raises RuntimeError on failure."""
    vs = compile_shader(vert_src, GL_VERTEX_SHADER)
    fs = compile_shader(frag_src, GL_FRAGMENT_SHADER)
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
