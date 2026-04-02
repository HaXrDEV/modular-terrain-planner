import glob
import logging
import math
import os
from typing import List, Tuple

import numpy as np

from models.tile_definition import TileDefinition

logger = logging.getLogger(__name__)


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


# Target triangle density in triangles per unit of normalised 3D surface area.
# Six tiers covering the full detail range.  Screen-coverage LOD selection
# picks the tier whose actual triangle count is closest to
# (pixel_area × _TRIS_PER_PIXEL) so detail scales with projected screen area.
_LOD_DENSITY = (50_000, 20_000, 8_000, 4_000, 2_500, 1_500)

# A mesh is only decimated for a given tier if its original density is at least
# this many times higher than that tier's target density.  Coarser tiers
# therefore require proportionally more source detail — low-quality meshes
# naturally fall through to their full resolution for all tiers where they
# don't meet the headroom requirement.
_LOD_QUALITY_HEADROOM = 5

# Reference grid used to calibrate per-mesh density before solving for the
# target grid.  A mid-range value keeps the calibration pass cheap.
_REF_GRID = 50


def _decimate(verts: np.ndarray, grid: int) -> np.ndarray:
    """
    Vertex-clustering decimation.  Merges vertices that fall in the same cell
    of a *grid*³ lattice, remaps triangles to the merged vertices, and removes
    any triangle that collapses to fewer than 3 distinct vertices.

    Because shared edges use the same representative vertices on both sides the
    surface stays watertight — no holes.

    verts : (N, 3, 3) float32  — normalised triangles
    returns (M, 3, 3) float32  — decimated triangles, M <= N
    """
    g = grid
    flat = verts.reshape(-1, 3).astype(np.float64)         # (N*3, 3)
    cell = np.clip((flat * g).astype(np.int32), 0, g - 1)
    keys = cell[:, 0] * g * g + cell[:, 1] * g + cell[:, 2]

    # Map each original vertex to its cluster's representative index
    unique_keys, inverse = np.unique(keys, return_inverse=True)

    # Compute each cluster's representative vertex (centroid of its members)
    rep = np.zeros((len(unique_keys), 3), dtype=np.float64)
    counts = np.zeros(len(unique_keys), dtype=np.int64)
    np.add.at(rep, inverse, flat)
    np.add.at(counts, inverse, 1)
    rep /= counts[:, np.newaxis]

    # Remap triangle indices; discard degenerate triangles
    tri_idx = inverse.reshape(-1, 3)                        # (N, 3)
    i0, i1, i2 = tri_idx[:, 0], tri_idx[:, 1], tri_idx[:, 2]
    valid = (i0 != i1) & (i1 != i2) & (i0 != i2)
    tri_idx = tri_idx[valid]

    return rep[tri_idx].astype(np.float32)                  # (M, 3, 3)


def _decimate_to_target(verts: np.ndarray, target: int,
                        original_density: float,
                        tier_density: float) -> np.ndarray:
    """
    Decimate *verts* to approximately *target* triangles.

    Decimation is skipped unless the mesh's original density is at least
    _LOD_QUALITY_HEADROOM× the tier's target density.  This means coarser
    tiers require proportionally more source detail — low-quality meshes
    are returned unchanged for any tier where they lack sufficient headroom,
    keeping their full (if limited) geometry rather than degrading further.

    For meshes that do qualify, runs one cheap reference decimation
    (at _REF_GRID³) then uses the surface-mesh scaling law (output ∝ grid²)
    to estimate the grid that hits *target* and runs a second decimation.
    """
    if len(verts) == 0:
        return verts

    # Skip decimation if the mesh doesn't have enough density headroom over
    # this tier's target — protects low-quality meshes from over-reduction.
    if original_density < tier_density * _LOD_QUALITY_HEADROOM:
        return verts

    ref = _decimate(verts, _REF_GRID)
    n_ref = len(ref)
    if n_ref == 0:
        return ref

    # Surface meshes: output ∝ grid²  →  grid_target = ref_grid × √(target/n_ref)
    grid = max(4, min(300, round(_REF_GRID * math.sqrt(target / max(n_ref, 1)))))
    if grid == _REF_GRID:
        return ref
    return _decimate(verts, grid)


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

    # Normalise winding using stored STL face normals so back-face culling works.
    # For each triangle: if the cross-product normal opposes the stored normal,
    # swap v1 and v2 to flip the winding.  Triangles with a zero stored normal
    # are left unchanged (can't determine intent).
    stored = m.normals.astype(np.float64)               # (N, 3)
    geo    = np.cross(verts[:, 1] - verts[:, 0],
                      verts[:, 2] - verts[:, 0])        # (N, 3)
    stored_len = np.linalg.norm(stored, axis=1)         # (N,)
    dots       = (geo * stored).sum(axis=1)             # (N,)
    flip       = (stored_len > 1e-6) & (dots < 0.0)
    verts[flip, 1], verts[flip, 2] = verts[flip, 2].copy(), verts[flip, 1].copy()

    sx = dx if dx > 0 else 1.0
    sy = dy if dy > 0 else 1.0
    sz = dz if dz > 0 else 1.0

    # Normalise in-place to [0, 1]³
    verts[:, :, 0] = (verts[:, :, 0] - min_x) / sx
    verts[:, :, 1] = (verts[:, :, 1] - min_y) / sy
    verts[:, :, 2] = (verts[:, :, 2] - min_z) / sz

    return verts.astype(np.float32)


def load_stl_folder(folder_path: str, errors: List[str] = None,
                    progress_cb=None) -> List[TileDefinition]:
    """
    Scan *folder_path* for .stl files (case-insensitive) and return a list of
    TileDefinition objects with bounding-box-derived grid sizes.

    Files that fail to parse are skipped. If *errors* is a list, a human-readable
    message is appended for each skipped file; otherwise failures are printed.
    """
    from stl import mesh as stl_mesh

    pattern_lower = os.path.join(folder_path, "*.stl")
    pattern_upper = os.path.join(folder_path, "*.STL")
    paths = sorted(set(glob.glob(pattern_lower) + glob.glob(pattern_upper)))

    definitions: List[TileDefinition] = []
    total = len(paths)
    if progress_cb:
        progress_cb(0, total)
    for idx, stl_path in enumerate(paths):
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
            # Actual 3D surface area of the normalised mesh (in [0,1]³ units)
            v0 = view_triangles[:, 0]
            v1 = view_triangles[:, 1]
            v2 = view_triangles[:, 2]
            surface_area = float(
                np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1).sum() * 0.5
            )
            surface_area = max(surface_area, 0.01)  # guard against degenerate meshes
            original_density = len(view_triangles) / surface_area
            lod_triangles = [
                _decimate_to_target(view_triangles, int(d * surface_area), original_density, d)
                for d in _LOD_DENSITY
            ]
            lod_tri_counts = [len(t) for t in lod_triangles]
        except (OSError, ValueError, ArithmeticError, RuntimeError) as exc:
            msg = f"{name}: {exc}"
            if errors is not None:
                errors.append(msg)
            else:
                logger.warning("Skipping '%s'", msg)
            if progress_cb:
                progress_cb(idx + 1, total)
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
            lod_triangles=lod_triangles,
            lod_tri_counts=lod_tri_counts,
        ))
        if progress_cb:
            progress_cb(idx + 1, total)

    return definitions
