import csv
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.grid_model import GridModel


def export_to_csv(grid_model: "GridModel", output_path: str) -> None:
    """
    Write a print-list CSV to *output_path*.

    Columns: filename, stl_path, count
    Rows are sorted alphabetically by tile name.
    """
    counts = grid_model.get_counts()  # {name: int}

    # Build a name → stl_path map from placed tiles for traceability
    path_map: dict = {}
    for pt in grid_model.all_placed():
        path_map[pt.definition.name] = pt.definition.stl_path

    rows = sorted(counts.items(), key=lambda x: x[0].lower())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "stl_path", "count"])
        for name, count in rows:
            writer.writerow([name, path_map.get(name, ""), count])
