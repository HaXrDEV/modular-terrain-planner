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


def load_stl_folder(folder_path: str) -> List[TileDefinition]:
    """
    Scan *folder_path* for .stl files (case-insensitive) and return a list of
    TileDefinition objects with bounding-box-derived grid sizes.

    Files that fail to parse are silently skipped with a printed warning.
    """
    pattern_lower = os.path.join(folder_path, "*.stl")
    pattern_upper = os.path.join(folder_path, "*.STL")
    paths = sorted(set(glob.glob(pattern_lower) + glob.glob(pattern_upper)))

    definitions: List[TileDefinition] = []
    for stl_path in paths:
        name = os.path.splitext(os.path.basename(stl_path))[0]
        try:
            dx, dy, _ = parse_bounding_box(stl_path)
            grid_w = mm_to_cells(dx)
            grid_h = mm_to_cells(dy)
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
        ))

    return definitions
