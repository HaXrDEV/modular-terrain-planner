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

PROJECT_VERSION = 1


def save_project(
    path: str,
    folders: List[str],
    placed_tiles,
) -> None:
    """
    Write the current session to *path* (.mtp / JSON).

    Parameters
    ----------
    path       : destination file path
    folders    : ordered list of loaded folder paths (tab order)
    placed_tiles : iterable of PlacedTile objects
    """
    data: Dict[str, Any] = {
        "version": PROJECT_VERSION,
        "folders": list(folders),
        "tiles": [
            {
                "stl_path": pt.definition.stl_path,
                "grid_x":   pt.grid_x,
                "grid_y":   pt.grid_y,
                "rotation": pt.rotation,
            }
            for pt in placed_tiles
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_project(path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Read a project file and return ``(folders, tile_records)``.

    ``folders`` is the ordered list of STL folder paths.
    ``tile_records`` is a list of dicts with keys:
        stl_path, grid_x, grid_y, rotation
    Raises ValueError / OSError on corrupt or missing files.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError("Invalid project file format.")

    folders = [str(f) for f in data.get("folders", [])]
    tiles   = [
        {
            "stl_path": str(t["stl_path"]),
            "grid_x":   int(t["grid_x"]),
            "grid_y":   int(t["grid_y"]),
            "rotation": int(t["rotation"]),
        }
        for t in data.get("tiles", [])
    ]
    return folders, tiles
