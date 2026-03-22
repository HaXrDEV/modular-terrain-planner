from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QStatusBar,
)
from PyQt5.QtCore import Qt

from models.grid_model import GridModel
from models.placed_tile import PlacedTile
from models.tile_definition import TileDefinition
from stl_loader.loader import load_stl_folder
from export.csv_exporter import export_to_csv
from gui.gl_grid_view import GLGridView
from gui.palette_panel import PalettePanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("D&D STL Dungeon Designer")
        self.resize(1200, 800)

        # State
        self._model = GridModel()
        self._selected_definition: Optional[TileDefinition] = None
        self._pending_rotation: int = 0

        # Multi-folder tracking
        # stl_path → TileDefinition; never removed so placed tiles keep their refs
        self._all_definitions: Dict[str, TileDefinition] = {}
        # folder path → list of stl_paths from that folder
        self._loaded_folders: Dict[str, List[str]] = {}

        # Widgets
        self._view = GLGridView(self._model)
        self._palette = PalettePanel()

        # Layout
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._palette)
        splitter.addWidget(self._view)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

        # Connections
        self._palette.tile_selected.connect(self._on_tile_selected)
        self._palette.load_folder_clicked.connect(self._on_load_folder)
        self._palette.export_clicked.connect(self._on_export)
        self._palette.tab_closed.connect(self._on_tab_closed)

        self._view.tile_place_requested.connect(self._on_tile_placed)
        self._view.tile_remove_requested.connect(self._on_tile_removed)
        self._view.rotate_requested.connect(self._on_rotate)

        self._update_status()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_load_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select STL folder")
        if not folder:
            return

        # Switch to existing tab if already loaded
        if folder in self._loaded_folders:
            self._palette.focus_folder_tab(folder)
            return

        definitions = load_stl_folder(folder)
        if not definitions:
            QMessageBox.warning(self, "No STL files", f"No .stl files found in:\n{folder}")
            return

        # Register truly new definitions and upload only those to GL
        new_defs = [d for d in definitions if d.stl_path not in self._all_definitions]
        for d in new_defs:
            self._all_definitions[d.stl_path] = d
        self._loaded_folders[folder] = [d.stl_path for d in definitions]

        if new_defs:
            self._view.add_definitions(new_defs)

        self._palette.add_folder_tab(folder, definitions)
        self._update_status()

    def _on_tile_selected(self, defn: Optional[TileDefinition]) -> None:
        self._selected_definition = defn
        self._pending_rotation = 0
        self._view.set_pending_tile(defn, 0)
        self._update_status()

    def _on_tile_placed(self, gx: int, gy: int) -> None:
        if self._selected_definition is None:
            return
        pt = PlacedTile(
            definition=self._selected_definition,
            grid_x=gx,
            grid_y=gy,
            rotation=self._pending_rotation,
        )
        self._model.place(pt)
        self._view.refresh()
        self._update_status()

    def _on_tile_removed(self, gx: int, gy: int) -> None:
        self._model.remove_at(gx, gy)
        self._view.refresh()
        self._update_status()

    def _on_rotate(self) -> None:
        self._pending_rotation = (self._pending_rotation + 90) % 360
        self._view.set_pending_tile(self._selected_definition, self._pending_rotation)
        self._update_status()

    def _on_tab_closed(self, folder_path: str) -> None:
        # Remove from loaded-folders registry so the folder can be re-loaded later.
        # _all_definitions is intentionally NOT modified: placed tiles still hold
        # Python references to TileDefinition objects and VBOs remain valid.
        self._loaded_folders.pop(folder_path, None)
        self._update_status()

    def _on_export(self) -> None:
        counts = self._model.get_counts()
        if not counts:
            QMessageBox.information(self, "Nothing to export", "Place some tiles first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "print_list.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            export_to_csv(self._model, path)
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        name = self._selected_definition.name if self._selected_definition else "None"
        counts = self._model.get_counts()
        total = sum(counts.values())
        counts_str = ", ".join(
            f"{k}: {v}" for k, v in sorted(counts.items())
        ) or "—"
        self._status.showMessage(
            f"Selected: {name}  |  Rotation: {self._pending_rotation}°  |  "
            f"Total placed: {total}  |  {counts_str}"
        )
        self._palette.update_info(
            self._pending_rotation,
            counts.get(name, 0) if self._selected_definition else 0,
        )
