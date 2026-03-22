import glob
import os
from typing import List, Tuple

from models.tile_definition import TileDefinition


def mm_to_cells(mm: float) -> int:
    """Convert millimetres to grid cells (1 cell = 25mm). Minimum 1."""
    return max(1, round(mm / 25.0))


def parse_bounding_box(stl_path: str) -> Tuple[float, float, float]:
    """
    Parse an STL file and return (dx_mm, dy_mm, dz_mm) bounding box dimensions.

    Applies an inches heuristic: if max(dx, dy) < 5.0 the file is likely authored
    in inches (common in OpenForge / Printable Scenery tiles), so dimensions are
    multiplied by 25.4 to convert to millimetres.
    """
    from stl import mesh as stl_mesh  # numpy-stl

    m = stl_mesh.Mesh.from_file(stl_path)
    dx = float(m.max_[0] - m.min_[0])
    dy = float(m.max_[1] - m.min_[1])
    dz = float(m.max_[2] - m.min_[2])

    # Inches heuristic
    if max(dx, dy) < 5.0 and max(dx, dy) > 0:
        dx *= 25.4
        dy *= 25.4
        dz *= 25.4

    return dx, dy, dz


def extract_top_view_triangles(
    stl_path: str,
    min_x: float,
    min_y: float,
    dx: float,
    dy: float,
) -> List[List[Tuple[float, float]]]:
    """
    Return all triangles of the mesh projected onto the XY plane, with each
    vertex normalised to [0, 1] relative to the bounding box.

    Large meshes are sub-sampled to at most MAX_TRIS triangles so rendering
    stays fast at any zoom level.
    """
    from stl import mesh as stl_mesh
    import numpy as np

    MAX_TRIS = 4000

    m = stl_mesh.Mesh.from_file(stl_path)
    # m.vectors shape: (n_triangles, 3, 3) — axis 2 is (x, y, z)
    verts = m.vectors  # keep as numpy for speed

    # Sub-sample if needed (evenly spaced)
    n = len(verts)
    if n > MAX_TRIS:
        idx = np.round(np.linspace(0, n - 1, MAX_TRIS)).astype(int)
        verts = verts[idx]

    # Avoid division by zero for degenerate meshes
    sx = dx if dx > 0 else 1.0
    sy = dy if dy > 0 else 1.0

    triangles = []
    for tri in verts:
        pts = [
            (float((tri[i][0] - min_x) / sx), float((tri[i][1] - min_y) / sy))
            for i in range(3)
        ]
        triangles.append(pts)

    return triangles


def load_stl_folder(folder_path: str) -> List[TileDefinition]:
    """
    Scan *folder_path* for .stl files (case-insensitive) and return a list of
    TileDefinition objects with bounding-box-derived grid sizes.

    Files that fail to parse are silently skipped with a printed warning.
    """
    from stl import mesh as stl_mesh

    pattern_lower = os.path.join(folder_path, "*.stl")
    pattern_upper = os.path.join(folder_path, "*.STL")
    paths = sorted(set(glob.glob(pattern_lower) + glob.glob(pattern_upper)))

    definitions: List[TileDefinition] = []
    for stl_path in paths:
        name = os.path.splitext(os.path.basename(stl_path))[0]
        try:
            m = stl_mesh.Mesh.from_file(stl_path)
            min_x, min_y = float(m.min_[0]), float(m.min_[1])
            dx = float(m.max_[0] - m.min_[0])
            dy = float(m.max_[1] - m.min_[1])
            dz = float(m.max_[2] - m.min_[2])

            # Inches heuristic
            scale = 1.0
            if max(dx, dy) < 5.0 and max(dx, dy) > 0:
                scale = 25.4
            dx *= scale
            dy *= scale
            dz *= scale

            grid_w = mm_to_cells(dx)
            grid_h = mm_to_cells(dy)
            view_triangles = extract_top_view_triangles(
                stl_path, min_x, min_y, dx / scale, dy / scale
            )
        except Exception as exc:
            print(f"[STL loader] Skipping '{name}': {exc}")
            continue

        color = TileDefinition.color_for_name(name)
        definitions.append(TileDefinition(
            name=name,
            stl_path=stl_path,
            grid_w=grid_w,
            grid_h=grid_h,
            color=color,
            view_triangles=view_triangles,
        ))

    return definitions
