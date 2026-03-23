"""
Project save / load for .mtp (Modular Terrain Planner) files.

A project file is a JSON document that captures:
  - The ordered list of loaded STL folders (tab order)
  - Every placed tile (stl_path + grid position + rotation)

On load, folders are re-scanned from disk and tiles are re-placed by
looking up each stl_path in the rebuilt definition map.
"""
import json
from typing import Any, Dict, List, Optional, Tuple

PROJECT_VERSION = 4


def save_project(
    path: str,
    folders: List[str],
    placed_tiles,
    grid_cols: int = 40,
    grid_rows: int = 40,
    ground_image: Optional[tuple] = None,
) -> None:
    """
    Write the current session to *path* (.mtp / JSON).

    Parameters
    ----------
    path         : destination file path
    folders      : ordered list of loaded folder paths (tab order)
    placed_tiles : iterable of PlacedTile objects
    grid_cols    : number of grid columns
    grid_rows    : number of grid rows
    ground_image : optional (path_str, [x, y, w, h]) tuple
    """
    data: Dict[str, Any] = {
        "version": PROJECT_VERSION,
        "grid_cols": grid_cols,
        "grid_rows": grid_rows,
        "folders": list(folders),
        "tiles": [
            {
                "stl_path": pt.definition.stl_path,
                "grid_x":   pt.grid_x,
                "grid_y":   pt.grid_y,
                "rotation": pt.rotation,
                "z_offset": pt.z_offset,
            }
            for pt in placed_tiles
        ],
    }
    if ground_image:
        data["ground_image"] = {"path": ground_image[0], "rect": list(ground_image[1])}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_project(path: str) -> Tuple[List[str], List[Dict[str, Any]], int, int, Optional[Dict[str, Any]]]:
    """
    Read a project file and return
    ``(folders, tile_records, grid_cols, grid_rows, ground_image)``.

    ``folders`` is the ordered list of STL folder paths.
    ``tile_records`` is a list of dicts with keys:
        stl_path, grid_x, grid_y, rotation, z_offset
    ``ground_image`` is None or {"path": str, "rect": [x, y, w, h]}.
    Raises ValueError / OSError on corrupt or missing files.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError("Invalid project file format.")

    grid_cols = int(data.get("grid_cols", 40))
    grid_rows = int(data.get("grid_rows", 40))
    folders = [str(f) for f in data.get("folders", [])]
    tiles   = [
        {
            "stl_path": str(t["stl_path"]),
            "grid_x":   float(t["grid_x"]),
            "grid_y":   float(t["grid_y"]),
            "rotation": int(t["rotation"]),
            "z_offset": float(t.get("z_offset", 0.0)),
        }
        for t in data.get("tiles", [])
    ]
    gi_raw = data.get("ground_image")
    ground_image: Optional[Dict[str, Any]] = None
    if isinstance(gi_raw, dict) and "path" in gi_raw and "rect" in gi_raw:
        ground_image = {
            "path": str(gi_raw["path"]),
            "rect": [float(v) for v in gi_raw["rect"]],
        }
    return folders, tiles, grid_cols, grid_rows, ground_image
