import os
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QAction, QMenuBar,
)

from models.grid_model import GridModel
from models.placed_tile import PlacedTile
from models.tile_definition import TileDefinition
from stl_loader.loader import load_stl_folder
from export.csv_exporter import export_to_csv
from persistence.settings import AppSettings
from persistence.project import save_project, load_project
from gui.gl_grid_view import GLGridView
from gui.palette_panel import PalettePanel

_FILTER = "Modular Terrain Planner project (*.mtp);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modular Terrain Planner")
        self.resize(1200, 800)

        # Persistent settings
        self._settings = AppSettings()
        self._settings.load()

        # State
        self._model = GridModel()
        self._selected_definition: Optional[TileDefinition] = None
        self._pending_rotation: int = 0
        self._project_path: Optional[str] = None
        self._is_dirty: bool = False

        # Multi-folder tracking
        self._all_definitions: Dict[str, TileDefinition] = {}
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

        # Menu bar
        self._build_menu()

        # Connections
        self._palette.tile_selected.connect(self._on_tile_selected)
        self._palette.load_folder_clicked.connect(self._on_load_folder)
        self._palette.export_clicked.connect(self._on_export_csv)
        self._palette.tab_closed.connect(self._on_tab_closed)

        self._view.tile_place_requested.connect(self._on_tile_placed)
        self._view.tile_remove_requested.connect(self._on_tile_removed)
        self._view.rotate_requested.connect(self._on_rotate)

        self._update_title()
        self._update_status()

        # Restore last session folders after the window has been shown
        # (deferred so the GL context has time to initialise)
        QTimer.singleShot(0, self._restore_session)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")

        act_new = QAction("&New", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._on_new)
        file_menu.addAction(act_new)

        file_menu.addSeparator()

        act_open = QAction("&Open Project…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._on_open)
        file_menu.addAction(act_open)

        act_save = QAction("&Save Project", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._on_save)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save Project &As…", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._on_save_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_load_folder = QAction("&Load STL Folder…", self)
        act_load_folder.setShortcut("Ctrl+L")
        act_load_folder.triggered.connect(self._on_load_folder)
        file_menu.addAction(act_load_folder)

        file_menu.addSeparator()

        act_export = QAction("&Export Print List (CSV)…", self)
        act_export.setShortcut("Ctrl+E")
        act_export.triggered.connect(self._on_export_csv)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

    # ------------------------------------------------------------------
    # Session restore
    # ------------------------------------------------------------------

    def _restore_session(self) -> None:
        """Silently reload folders from the last session."""
        missing: List[str] = []
        for folder in self._settings.recent_folders:
            if os.path.isdir(folder):
                self._load_folder_silent(folder)
            else:
                missing.append(folder)
        for folder in missing:
            self._settings.remove_folder(folder)

    # ------------------------------------------------------------------
    # Project helpers
    # ------------------------------------------------------------------

    def _load_folder_silent(self, folder: str) -> None:
        """Load a folder without showing an error dialog on failure."""
        if folder in self._loaded_folders:
            return
        try:
            definitions = load_stl_folder(folder)
        except Exception:
            return
        if not definitions:
            return
        new_defs = [d for d in definitions if d.stl_path not in self._all_definitions]
        for d in new_defs:
            self._all_definitions[d.stl_path] = d
        self._loaded_folders[folder] = [d.stl_path for d in definitions]
        if new_defs:
            self._view.add_definitions(new_defs)
        self._palette.add_folder_tab(folder, definitions)

    def _apply_project(self, folders: list, tile_records: list) -> None:
        """
        Clear the current session and apply a loaded project.
        Missing folders or unresolvable stl_paths are skipped with a warning.
        """
        self._on_new(confirm=False)

        missing_folders = []
        for folder in folders:
            if os.path.isdir(folder):
                self._load_folder_silent(folder)
                self._settings.add_folder(folder)
            else:
                missing_folders.append(folder)

        skipped = 0
        for rec in tile_records:
            defn = self._all_definitions.get(rec["stl_path"])
            if defn is None:
                skipped += 1
                continue
            pt = PlacedTile(
                definition=defn,
                grid_x=rec["grid_x"],
                grid_y=rec["grid_y"],
                rotation=rec["rotation"],
            )
            self._model.place(pt)

        self._view.refresh()
        self._update_status()

        warnings = []
        if missing_folders:
            warnings.append(f"Folders not found ({len(missing_folders)}):\n" +
                            "\n".join(f"  {f}" for f in missing_folders))
        if skipped:
            warnings.append(f"{skipped} tile(s) could not be placed (STL not found).")
        if warnings:
            QMessageBox.warning(self, "Project loaded with issues", "\n\n".join(warnings))

    def _confirm_discard(self) -> bool:
        """Ask the user whether to discard unsaved changes. Returns True if OK to proceed."""
        if not self._is_dirty:
            return True
        btn = QMessageBox.question(
            self, "Unsaved changes",
            "The current project has unsaved changes.\nDiscard and continue?",
            QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return btn == QMessageBox.Discard

    def _mark_dirty(self) -> None:
        if not self._is_dirty:
            self._is_dirty = True
            self._update_title()

    def _update_title(self) -> None:
        name = os.path.basename(self._project_path) if self._project_path else "Untitled"
        dirty = " *" if self._is_dirty else ""
        self.setWindowTitle(f"Modular Terrain Planner — {name}{dirty}")

    # ------------------------------------------------------------------
    # File menu slots
    # ------------------------------------------------------------------

    def _on_new(self, *, confirm: bool = True) -> None:
        if confirm and not self._confirm_discard():
            return
        self._model.clear()
        self._all_definitions.clear()
        self._loaded_folders.clear()
        self._selected_definition = None
        self._pending_rotation = 0
        self._project_path = None
        self._is_dirty = False
        # Rebuild palette (clear all tabs) and GL cache
        self._palette.clear_all_tabs()
        self._view.load_definitions([])
        self._update_title()
        self._update_status()

    def _on_open(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", _FILTER)
        if not path:
            return
        try:
            folders, tile_records = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._apply_project(folders, tile_records)
        self._project_path = path
        self._is_dirty = False
        self._update_title()

    def _on_save(self) -> None:
        if self._project_path:
            self._write_project(self._project_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", _FILTER)
        if not path:
            return
        if not path.endswith(".mtp"):
            path += ".mtp"
        self._write_project(path)

    def _write_project(self, path: str) -> None:
        try:
            folders = [self._palette.folder_for_tab(i)
                       for i in range(self._palette.tab_count())
                       if self._palette.folder_for_tab(i)]
            save_project(path, folders, self._model.all_placed())
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._project_path = path
        self._is_dirty = False
        self._update_title()

    # ------------------------------------------------------------------
    # Folder / palette slots
    # ------------------------------------------------------------------

    def _on_load_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select STL folder")
        if not folder:
            return
        if folder in self._loaded_folders:
            self._palette.focus_folder_tab(folder)
            return
        definitions = load_stl_folder(folder)
        if not definitions:
            QMessageBox.warning(self, "No STL files", f"No .stl files found in:\n{folder}")
            return
        new_defs = [d for d in definitions if d.stl_path not in self._all_definitions]
        for d in new_defs:
            self._all_definitions[d.stl_path] = d
        self._loaded_folders[folder] = [d.stl_path for d in definitions]
        if new_defs:
            self._view.add_definitions(new_defs)
        self._palette.add_folder_tab(folder, definitions)
        self._settings.add_folder(folder)
        self._update_status()

    def _on_tab_closed(self, folder_path: str) -> None:
        self._loaded_folders.pop(folder_path, None)
        self._update_status()

    # ------------------------------------------------------------------
    # Grid slots
    # ------------------------------------------------------------------

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
        self._mark_dirty()
        self._update_status()

    def _on_tile_removed(self, gx: int, gy: int) -> None:
        self._model.remove_at(gx, gy)
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_rotate(self) -> None:
        self._pending_rotation = (self._pending_rotation + 90) % 360
        self._view.set_pending_tile(self._selected_definition, self._pending_rotation)
        self._update_status()

    def _on_export_csv(self) -> None:
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
    # Window close
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._is_dirty:
            btn = QMessageBox.question(
                self, "Unsaved changes",
                "Save project before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if btn == QMessageBox.Cancel:
                event.ignore()
                return
            if btn == QMessageBox.Save:
                self._on_save()
                if self._is_dirty:   # save was cancelled
                    event.ignore()
                    return
        event.accept()

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
