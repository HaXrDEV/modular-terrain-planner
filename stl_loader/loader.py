import glob
import os
from typing import List, Tuple

import numpy as np

from models.tile_definition import TileDefinition


def mm_to_cells(mm: float) -> int:
    """Convert millimetres to grid cells (1 cell = 12.5mm). Minimum 1."""
    return max(1, round(mm / 12.5))


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


def load_tile_mesh(
    stl_path: str,
    min_x: float,
    min_y: float,
    min_z: float,
    dx: float,
    dy: float,
    dz: float,
) -> np.ndarray:
    """
    Load an STL file and return the full normalised (N, 3, 3) float32 array.

    Each vertex is normalised to [0, 1] in XYZ relative to the bounding box:
      nx = (x - min_x) / dx,  ny = (y - min_y) / dy,  nz = (z - min_z) / dz
    nz = 0 is the floor; nz = 1 is the tallest point.
    """
    from stl import mesh as stl_mesh

    m = stl_mesh.Mesh.from_file(stl_path)
    verts = m.vectors.astype(np.float64)  # (N, 3, 3)

    sx = dx if dx > 0 else 1.0
    sy = dy if dy > 0 else 1.0
    sz = dz if dz > 0 else 1.0

    # Normalise in-place
    verts[:, :, 0] = (verts[:, :, 0] - min_x) / sx
    verts[:, :, 1] = (verts[:, :, 1] - min_y) / sy
    verts[:, :, 2] = (verts[:, :, 2] - min_z) / sz

    return verts.astype(np.float32)


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
            min_x, min_y, min_z = float(m.min_[0]), float(m.min_[1]), float(m.min_[2])
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
            grid_z = max(0.1, dz / 12.5)   # height in grid-cell units
            view_triangles = load_tile_mesh(
                stl_path, min_x, min_y, min_z, dx / scale, dy / scale, dz / scale
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
            grid_z=grid_z,
            color=color,
            view_triangles=view_triangles,
        ))

    return definitions
