import math
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QImageReader
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QMenuBar, QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
    QDoubleSpinBox, QToolBar, QSlider, QLabel, QProgressDialog, QApplication,
)

from gui.style import WIN11_STYLESHEET, DARK_STYLESHEET
from models.grid_model import GridModel
from models.placed_tile import PlacedTile
from models.tile_definition import TileDefinition
from stl_loader.loader import load_stl_folder
from stl_loader.worker import STLLoaderWorker
from export.csv_exporter import export_to_csv
from export.assembly_map import export_assembly_map, export_assembly_pdf
from persistence.settings import AppSettings
from persistence.project import save_project, load_project, TileRecord, GroundImageRecord
from gui.gl_grid_view import GLGridView
from gui.palette_panel import PalettePanel
from gui.missing_folders_dialog import MissingFoldersDialog

_FILTER = "Modular Terrain Planner project (*.mtp);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Modular Terrain Planner")
        self.setMinimumSize(900, 600)
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
        self._ground_image: Optional[tuple] = None  # (path, [x, y, w, h])
        self._ground_image_aspect: float = 1.0
        self._free_mode: bool = False

        # Undo / redo stacks — each entry is a state snapshot dict
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        _MAX_UNDO = 100

        # Copy / paste clipboard: list of (TileDefinition, rel_x, rel_y, rotation, rel_z)
        self._clipboard: list = []

        # Multi-folder tracking
        self._all_definitions: Dict[str, TileDefinition] = {}
        self._loaded_folders: Dict[str, List[str]] = {}
        self._loading_workers: List[STLLoaderWorker] = []

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

        # Ground image toolbar (hidden until an image is loaded)
        self._img_toolbar = QToolBar("Ground Image", self)
        self._img_toolbar.setMovable(False)
        self._img_toolbar.addWidget(QLabel("  Battle map scale: "))
        self._img_scale_slider = QSlider(Qt.Horizontal)
        self._img_scale_slider.setRange(10, 8000)   # internal = cells × 10
        self._img_scale_slider.setValue(self._model.GRID_COLS * 10)
        self._img_scale_slider.setFixedWidth(400)
        self._img_scale_slider.setToolTip("Image width in grid cells")
        self._img_toolbar.addWidget(self._img_scale_slider)
        self._img_scale_label = QLabel("  80 cells  ")
        self._img_toolbar.addWidget(self._img_scale_label)
        self._img_toolbar.addWidget(QLabel("  (Alt + drag to move)"))
        self.addToolBar(Qt.TopToolBarArea, self._img_toolbar)
        self._img_toolbar.hide()

        # Connections
        self._palette.tile_selected.connect(self._on_tile_selected)
        self._palette.load_folder_clicked.connect(self._on_load_folder)
        self._palette.export_clicked.connect(self._on_export_assembly_pdf)
        self._palette.tab_closed.connect(self._on_tab_closed)

        self._view.tile_place_requested.connect(self._on_tile_placed)
        self._view.tile_remove_requested.connect(self._on_tile_removed)
        self._view.tile_pickup_requested.connect(self._on_tile_pickup)
        self._view.tiles_move_requested.connect(self._on_tiles_moved)
        self._view.selection_delete_requested.connect(self._on_selection_delete)
        self._view.select_all_requested.connect(self._on_select_all)
        self._view.zoom_fit_requested.connect(self._on_zoom_fit)
        self._view.free_mode_changed.connect(self._on_free_mode_changed)
        self._view.selection_rotate_requested.connect(self._on_selection_rotate)
        self._view.rotate_requested.connect(self._on_rotate)
        self._view.deselect_requested.connect(self._on_deselect)
        self._view.paste_place_requested.connect(self._on_paste_place)
        self._view.ground_image_rect_changed.connect(self._on_ground_image_moved)
        self._view.ground_image_drag_started.connect(self._snapshot)

        self._img_scale_slider.valueChanged.connect(self._on_img_scale_changed)

        self._view.set_pan_speed(self._settings.pan_speed)
        self._apply_theme(self._settings.theme)

        # Re-apply theme when the OS colour scheme changes at runtime
        try:
            QApplication.instance().styleHints().colorSchemeChanged.connect(
                self._on_system_theme_changed
            )
        except AttributeError:
            pass  # Qt < 6.5

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

        self._recent_menu = file_menu.addMenu("&Recent Projects")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        act_load_folder = QAction("&Load STL Folder…", self)
        act_load_folder.setShortcut("Ctrl+L")
        act_load_folder.triggered.connect(self._on_load_folder)
        file_menu.addAction(act_load_folder)

        file_menu.addSeparator()

        act_export_pdf = QAction("Export &Build Plan (PDF)\u2026", self)
        act_export_pdf.setShortcut("Ctrl+E")
        act_export_pdf.triggered.connect(self._on_export_assembly_pdf)
        file_menu.addAction(act_export_pdf)

        act_export = QAction("&Export Print List (CSV)…", self)
        act_export.setShortcut("Ctrl+Shift+E")
        act_export.triggered.connect(self._on_export_csv)
        file_menu.addAction(act_export)

        act_export_map = QAction("Export &Assembly Map (PNG)\u2026", self)
        act_export_map.triggered.connect(self._on_export_assembly_map)
        file_menu.addAction(act_export_map)

        file_menu.addSeparator()

        act_quit = QAction("&Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit menu
        edit_menu = mb.addMenu("&Edit")

        self._act_undo = QAction("&Undo", self)
        self._act_undo.setShortcut("Ctrl+Z")
        self._act_undo.setEnabled(False)
        self._act_undo.triggered.connect(self._on_undo)
        edit_menu.addAction(self._act_undo)

        self._act_redo = QAction("&Redo", self)
        self._act_redo.setShortcut("Ctrl+Y")
        self._act_redo.setEnabled(False)
        self._act_redo.triggered.connect(self._on_redo)
        edit_menu.addAction(self._act_redo)

        edit_menu.addSeparator()

        self._act_copy = QAction("&Copy", self)
        self._act_copy.setShortcut("Ctrl+C")
        self._act_copy.triggered.connect(self._on_copy)
        edit_menu.addAction(self._act_copy)

        self._act_paste = QAction("&Paste", self)
        self._act_paste.setShortcut("Ctrl+V")
        self._act_paste.triggered.connect(self._on_paste)
        edit_menu.addAction(self._act_paste)

        act_select_all = QAction("Select &All", self)
        act_select_all.setShortcut("Ctrl+A")
        act_select_all.triggered.connect(self._on_select_all)
        edit_menu.addAction(act_select_all)

        edit_menu.addSeparator()

        act_grid_size = QAction("&Grid Size…", self)
        act_grid_size.triggered.connect(self._on_grid_size)
        edit_menu.addAction(act_grid_size)

        act_cam_speed = QAction("&Camera Speed…", self)
        act_cam_speed.triggered.connect(self._on_camera_speed)
        edit_menu.addAction(act_cam_speed)

        edit_menu.addSeparator()

        act_set_img = QAction("Set &Ground Image…", self)
        act_set_img.triggered.connect(self._on_set_ground_image)
        edit_menu.addAction(act_set_img)

        act_clear_img = QAction("&Clear Ground Image", self)
        act_clear_img.triggered.connect(self._on_clear_ground_image)
        edit_menu.addAction(act_clear_img)

        # View menu
        view_menu = mb.addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")

        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        self._act_theme_auto  = QAction("&Automatic", self)
        self._act_theme_light = QAction("&Light",     self)
        self._act_theme_dark  = QAction("&Dark",      self)
        for act in (self._act_theme_auto, self._act_theme_light, self._act_theme_dark):
            act.setCheckable(True)
            theme_group.addAction(act)
            theme_menu.addAction(act)

        self._act_theme_auto.triggered.connect(lambda: self._apply_theme("auto"))
        self._act_theme_light.triggered.connect(lambda: self._apply_theme("light"))
        self._act_theme_dark.triggered.connect(lambda: self._apply_theme("dark"))

        view_menu.addSeparator()

        self._act_ortho = QAction("&Top-down (Orthographic)", self)
        self._act_ortho.setCheckable(True)
        self._act_ortho.setShortcut("5")
        self._act_ortho.triggered.connect(self._on_toggle_ortho)
        view_menu.addAction(self._act_ortho)

        # Debug menu
        debug_menu = mb.addMenu("&Debug")

        self._act_ortho_proj = QAction("&Orthographic projection (normal camera)", self)
        self._act_ortho_proj.setCheckable(True)
        self._act_ortho_proj.triggered.connect(self._on_toggle_ortho_proj)
        debug_menu.addAction(self._act_ortho_proj)

        debug_menu.addSeparator()

        self._act_disable_lod = QAction("&Disable LOD (force full detail)", self)
        self._act_disable_lod.setCheckable(True)
        self._act_disable_lod.triggered.connect(self._on_toggle_lod)
        debug_menu.addAction(self._act_disable_lod)

    def _on_toggle_ortho(self, checked: bool) -> None:
        self._view.set_ortho_mode(checked)

    def _on_toggle_ortho_proj(self, checked: bool) -> None:
        self._view.set_ortho_proj(checked)

    def _on_toggle_lod(self, checked: bool) -> None:
        self._view.lod_disabled = checked
        self._view.refresh()

    # ------------------------------------------------------------------
    # Session restore
    # ------------------------------------------------------------------

    def _restore_session(self) -> None:
        """Reload folders from the last session, showing a progress dialog."""
        missing: List[str] = []
        present: List[str] = []
        for folder in self._settings.recent_folders:
            if os.path.isdir(folder):
                present.append(folder)
            else:
                missing.append(folder)
        for folder in missing:
            self._settings.remove_folder(folder)

        if not present:
            return

        total = len(present)
        progress = QProgressDialog("Restoring session…", None, 0, total, self)
        progress.setWindowTitle("Loading")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        completed = [0]

        def _folder_done(*_) -> None:
            completed[0] += 1
            progress.setValue(completed[0])
            if completed[0] >= total:
                progress.close()

        def _start(folder: str) -> None:
            w = STLLoaderWorker(folder, parent=self)
            w.finished.connect(
                lambda f, defs, errs: self._on_folder_loaded(f, defs, errs, silent=True))
            w.finished.connect(_folder_done)
            w.failed.connect(_folder_done)
            w.finished.connect(lambda: self._cleanup_worker(w))
            w.failed.connect(lambda: self._cleanup_worker(w))
            self._loading_workers.append(w)
            w.start()

        for folder in present:
            _start(folder)

    # ------------------------------------------------------------------
    # Project helpers
    # ------------------------------------------------------------------

    def _load_folder_sync(self, folder: str) -> None:
        """Load a folder synchronously (blocks until done).

        Used by project loading which needs definitions available immediately
        so tile records can be resolved against them.
        """
        if folder in self._loaded_folders:
            return
        try:
            errors: list = []
            definitions = load_stl_folder(folder, errors=errors)
        except (OSError, ValueError, RuntimeError):
            return
        if not definitions:
            return
        self._on_folder_loaded(folder, definitions, errors, silent=True)

    def _start_folder_load(self, folder: str) -> None:
        """Launch a background worker to load *folder*."""
        worker = STLLoaderWorker(folder, parent=self)
        worker.finished.connect(
            lambda f, defs, errs: self._on_folder_loaded(f, defs, errs))
        worker.failed.connect(self._on_folder_load_failed)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.failed.connect(lambda: self._cleanup_worker(worker))
        self._loading_workers.append(worker)

        basename = os.path.basename(folder)
        dlg = QProgressDialog(f"Loading '{basename}'…", "Cancel", 0, 0, self)
        dlg.setWindowTitle("Loading STL Folder")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def _on_progress(current: int, total: int) -> None:
            dlg.setMaximum(total)
            dlg.setValue(current)

        worker.progress.connect(_on_progress)
        worker.finished.connect(lambda *_: dlg.close())
        worker.failed.connect(lambda *_: dlg.close())
        dlg.canceled.connect(worker.cancel)
        dlg.show()

        worker.start()

    def _on_folder_loaded(self, folder: str, definitions: list,
                          errors: list = None, *, silent: bool = False) -> None:
        """Callback when a background folder load finishes successfully."""
        if folder in self._loaded_folders:
            return
        new_defs = [d for d in definitions if d.stl_path not in self._all_definitions]
        for d in new_defs:
            self._all_definitions[d.stl_path] = d
        self._loaded_folders[folder] = [d.stl_path for d in definitions]
        if new_defs:
            self._view.add_definitions(new_defs)
        self._palette.add_folder_tab(folder, definitions)
        if not silent:
            self._palette.focus_folder_tab(folder)
            self._settings.add_folder(folder)
            self._update_status()
        if errors:
            basename = os.path.basename(folder)
            detail = "\n".join(f"  \u2022 {e}" for e in errors)
            QMessageBox.warning(
                self, "Some STL files skipped",
                f"{len(errors)} file(s) in '{basename}' could not be loaded:\n\n{detail}"
            )

    def _on_folder_load_failed(self, folder: str, error: str) -> None:
        """Callback when a background folder load fails."""
        if error != "Cancelled":
            QMessageBox.warning(self, "No STL files",
                                f"No .stl files found in:\n{folder}\n\n{error}")
            self._update_status()

    def _cleanup_worker(self, worker: STLLoaderWorker) -> None:
        if worker in self._loading_workers:
            self._loading_workers.remove(worker)
        worker.deleteLater()

    def _apply_project(self, folders: List[str], tile_records: List[TileRecord],
                       grid_cols: int = 40, grid_rows: int = 40,
                       ground_image: Optional[GroundImageRecord] = None) -> None:
        """
        Clear the current session and apply a loaded project.
        Missing folders or unresolvable stl_paths are skipped with a warning.
        """
        self._on_new(confirm=False)
        self._model.GRID_COLS = grid_cols
        self._model.GRID_ROWS = grid_rows
        self._view.rebuild_grid_geometry()

        missing_folders = [f for f in folders if not os.path.isdir(f)]
        present_folders  = [f for f in folders if     os.path.isdir(f)]

        # Offer folder remapping before loading anything
        remapping: dict = {}
        if missing_folders:
            dlg = MissingFoldersDialog(missing_folders, parent=self)
            if dlg.exec() == QDialog.Accepted:
                remapping = dlg.remapping()

        still_missing = [f for f in missing_folders if f not in remapping]

        resolved = present_folders + [remapping.get(f, f) for f in missing_folders]
        valid_folders = [f for f in resolved if os.path.isdir(f)]
        if valid_folders:
            progress = QProgressDialog("Loading project…", None, 0, len(valid_folders), self)
            progress.setWindowTitle("Opening Project")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            for i, folder in enumerate(valid_folders):
                progress.setLabelText(f"Loading '{os.path.basename(folder)}'… ({i + 1}/{len(valid_folders)})")
                progress.setValue(i)
                QApplication.processEvents()
                self._load_folder_sync(folder)
                self._settings.add_folder(folder)
            progress.setValue(len(valid_folders))
            progress.close()

        missing_tiles: list = []
        for rec in tile_records:
            stl_path = rec.stl_path
            for old, new in remapping.items():
                if stl_path.startswith(old):
                    stl_path = new + stl_path[len(old):]
                    break
            defn = self._all_definitions.get(stl_path)
            if defn is None:
                missing_tiles.append(stl_path)
                continue
            pt = PlacedTile(
                definition=defn,
                grid_x=rec.grid_x,
                grid_y=rec.grid_y,
                rotation=rec.rotation,
                z_offset=rec.z_offset,
            )
            self._model.place(pt)

        self._view.refresh()
        self._update_status()

        # Restore ground image
        if ground_image and os.path.isfile(ground_image.path):
            rect = ground_image.rect
            self._view.set_ground_image(ground_image.path, rect)
            self._ground_image = (ground_image.path, rect)
            self._ground_image_aspect = rect[2] / max(rect[3], 1e-6)
            self._show_img_toolbar(rect)
        else:
            self._ground_image = None
            self._img_toolbar.hide()

        warnings = []
        if still_missing:
            warnings.append(
                f"{len(still_missing)} folder(s) skipped:\n" +
                "\n".join(f"  {f}" for f in still_missing)
            )
        if missing_tiles:
            # Count occurrences per (folder, filename) so each tile shows once
            by_folder: dict = {}
            for p in missing_tiles:
                folder = os.path.dirname(p)
                name = os.path.basename(p)
                key = (folder, name)
                by_folder[key] = by_folder.get(key, 0) + 1
            lines = []
            current_folder = None
            for (folder, name), count in sorted(by_folder.items()):
                if folder != current_folder:
                    lines.append(f"  {folder}/")
                    current_folder = folder
                suffix = f" (\u00d7{count})" if count > 1 else ""
                lines.append(f"    \u2022 {name}{suffix}")
            unique = len(by_folder)
            total = len(missing_tiles)
            warnings.append(
                f"{total} placement(s) across {unique} tile(s) could not be "
                f"resolved (STL file not found):\n" + "\n".join(lines)
            )
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

    # ------------------------------------------------------------------
    # Undo / redo  (command-based — stores deltas instead of full state)
    # ------------------------------------------------------------------

    def _snapshot(self) -> None:
        """Capture a delta between the current state and what will follow.

        The delta records only the tiles, ground image, and grid size at the
        moment *before* the upcoming mutation.  Undo replays these small diffs
        instead of rebuilding the full tile list each time.
        """
        snap = self._capture_state()
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_actions()

    def _capture_state(self) -> dict:
        """Lightweight state capture — stores tile tuples for current placed list."""
        return {
            "tiles": [
                (pt.definition, pt.grid_x, pt.grid_y, pt.rotation, pt.z_offset)
                for pt in self._model.all_placed()
            ],
            "ground_image": self._ground_image,
            "grid_cols": self._model.GRID_COLS,
            "grid_rows": self._model.GRID_ROWS,
        }

    def _restore(self, snap: dict) -> None:
        """Restore application state from a snapshot."""
        cols, rows = snap["grid_cols"], snap["grid_rows"]
        size_changed = (cols != self._model.GRID_COLS or rows != self._model.GRID_ROWS)
        self._model.GRID_COLS = cols
        self._model.GRID_ROWS = rows
        self._model.clear()
        for defn, gx, gy, rot, z_off in snap["tiles"]:
            self._model.force_place(PlacedTile(defn, gx, gy, rot, z_off))
        if size_changed:
            self._view.rebuild_grid_geometry()
        gi = snap["ground_image"]
        if gi != self._ground_image:
            if gi:
                self._view.set_ground_image(gi[0], gi[1])
                self._ground_image = gi
                self._ground_image_aspect = gi[1][2] / max(gi[1][3], 1e-6)
                self._show_img_toolbar(gi[1])
            else:
                self._view.clear_ground_image()
                self._ground_image = None
                self._img_toolbar.hide()
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _update_undo_actions(self) -> None:
        self._act_undo.setEnabled(bool(self._undo_stack))
        self._act_redo.setEnabled(bool(self._redo_stack))

    def _on_undo(self) -> None:
        if not self._undo_stack:
            return
        self._redo_stack.append(self._capture_state())
        self._restore(self._undo_stack.pop())
        self._update_undo_actions()

    def _on_redo(self) -> None:
        if not self._redo_stack:
            return
        self._undo_stack.append(self._capture_state())
        self._restore(self._redo_stack.pop())
        self._update_undo_actions()

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
        self._ground_image = None
        self._img_toolbar.hide()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_undo_actions()
        # Rebuild palette (clear all tabs) and GL cache
        self._palette.clear_all_tabs()
        self._view.clear_selection()
        self._view.load_definitions([])
        self._view.clear_ground_image()
        self._update_title()
        self._update_status()

    def _on_open(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", _FILTER)
        if not path:
            return
        try:
            folders, tile_records, grid_cols, grid_rows, ground_image = load_project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._apply_project(folders, tile_records, grid_cols, grid_rows, ground_image)
        self._project_path = path
        self._is_dirty = False
        self._settings.add_project(path)
        self._rebuild_recent_menu()
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
            save_project(path, folders, self._model.all_placed(),
                         self._model.GRID_COLS, self._model.GRID_ROWS,
                         self._ground_image)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self._project_path = path
        self._is_dirty = False
        self._settings.add_project(path)
        self._rebuild_recent_menu()
        self._update_title()

    def _rebuild_recent_menu(self) -> None:
        """Rebuild the File → Recent Projects submenu from settings."""
        self._recent_menu.clear()
        for path in self._settings.recent_projects:
            if not os.path.isfile(path):
                continue
            name = os.path.basename(path)
            act = QAction(name, self)
            act.setToolTip(path)
            act.triggered.connect(lambda _checked, p=path: self._open_recent(p))
            self._recent_menu.addAction(act)
        self._recent_menu.setEnabled(bool(self._recent_menu.actions()))

    def _open_recent(self, path: str) -> None:
        """Open a project from the recent list."""
        if not self._confirm_discard():
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "File not found", f"Project file no longer exists:\n{path}")
            return
        try:
            folders, tile_records, grid_cols, grid_rows, ground_image = load_project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._apply_project(folders, tile_records, grid_cols, grid_rows, ground_image)
        self._project_path = path
        self._is_dirty = False
        self._settings.add_project(path)
        self._rebuild_recent_menu()
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
        self._start_folder_load(folder)

    def _on_tab_closed(self, folder_path: str) -> None:
        stl_paths = self._loaded_folders.pop(folder_path, [])
        # Free GPU resources for tiles that are no longer needed by any folder
        still_used = set()
        for paths in self._loaded_folders.values():
            still_used.update(paths)
        to_free = [p for p in stl_paths if p not in still_used]
        if to_free:
            self._view.remove_definitions(to_free)
            for p in to_free:
                self._all_definitions.pop(p, None)
        self._settings.remove_folder(folder_path)
        self._update_status()

    # ------------------------------------------------------------------
    # Grid slots
    # ------------------------------------------------------------------

    def _on_tile_selected(self, defn: Optional[TileDefinition]) -> None:
        self._selected_definition = defn
        self._pending_rotation = 0
        self._view.set_pending_tile(defn, 0)
        self._view.setFocus()
        self._update_status()

    def _on_deselect(self) -> None:
        self._selected_definition = None
        self._pending_rotation = 0
        self._palette.deselect()
        self._view.set_pending_tile(None, 0)
        self._update_status()

    def _on_select_all(self) -> None:
        self._view.set_selection(set(self._model.all_placed()))

    def _on_zoom_fit(self) -> None:
        """Frame the camera around the selection, or all placed tiles, or the full grid."""
        selection = list(self._view.selected_tiles())
        tiles = selection if selection else self._model.all_placed()
        if tiles:
            min_x = min(pt.grid_x for pt in tiles)
            min_y = min(pt.grid_y for pt in tiles)
            max_x = max(pt.grid_x + pt.effective_w for pt in tiles)
            max_y = max(pt.grid_y + pt.effective_h for pt in tiles)
        else:
            min_x, min_y = 0.0, 0.0
            max_x = float(self._model.GRID_COLS)
            max_y = float(self._model.GRID_ROWS)
        self._view.zoom_to_bounds(min_x, min_y, max_x, max_y)

    def _on_tile_pickup(self, tile) -> None:
        """Middle-click: select the picked-up tile's definition and rotation."""
        self._pending_rotation = tile.rotation
        # select_definition may trigger _on_tile_selected(None) via tab-change
        # signal, clearing _selected_definition — so assign it afterwards.
        self._palette.select_definition(tile.definition)
        self._selected_definition = tile.definition
        self._view.set_pending_tile(tile.definition, tile.rotation)
        self._view.setFocus()
        self._update_status()

    def _on_tile_placed(self, gx: float, gy: float) -> None:
        if self._selected_definition is None:
            return
        self._snapshot()
        from PySide6.QtWidgets import QApplication
        free = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
        igx, igy = int(math.floor(gx)), int(math.floor(gy))
        pt = PlacedTile(
            definition=self._selected_definition,
            grid_x=gx,
            grid_y=gy,
            rotation=self._pending_rotation,
            z_offset=self._model.top_z_at(igx, igy),
        )
        if free:
            self._model.force_place(pt)
        else:
            self._model.place(pt)
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_tile_removed(self, tile) -> None:
        self._snapshot()
        self._model.remove_tile(tile)
        self._view.discard_from_selection(tile)
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_selection_delete(self) -> None:
        if not self._view.has_selection():
            return
        self._snapshot()
        for tile in list(self._view.selected_tiles()):
            self._model.remove_tile(tile)
        self._view.clear_selection()
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_tiles_moved(self, moves: list) -> None:
        """moves: list of (PlacedTile, new_gx, new_gy, new_rotation)"""
        self._snapshot()
        new_tiles = []
        for tile, new_gx, new_gy, new_rot in moves:
            self._model.remove_tile(tile)
            new_tile = PlacedTile(tile.definition, new_gx, new_gy,
                                  new_rot, tile.z_offset)
            self._model.force_place(new_tile)
            new_tiles.append(new_tile)
        # Update selection to the newly created PlacedTile objects
        self._view.set_selection(set(new_tiles))
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_copy(self) -> None:
        selection = list(self._view.selected_tiles())
        if not selection:
            return
        # Store positions relative to the group centroid.
        # Floor the centroid so relative offsets are always integers for
        # grid-snapped tiles — prevents pasted tiles landing between grid lines.
        cx = math.floor(sum(t.grid_x + t.effective_w / 2.0 for t in selection) / len(selection))
        cy = math.floor(sum(t.grid_y + t.effective_h / 2.0 for t in selection) / len(selection))
        min_z = min(t.z_offset for t in selection)
        self._clipboard = [
            (t.definition, t.grid_x - cx, t.grid_y - cy, t.rotation, t.z_offset - min_z)
            for t in selection
        ]

    def _on_paste(self) -> None:
        if not self._clipboard:
            return
        # Enter ghost-paste mode — ghosts follow the cursor until left-click or Escape
        self._view.set_paste_buffer(list(self._clipboard))

    def _on_paste_place(self, cx: float, cy: float) -> None:
        """Called when the user left-clicks during paste ghost mode."""
        paste_buf = self._view.paste_buffer()
        if not paste_buf:
            self._view.set_paste_buffer(None)
            return
        self._snapshot()
        new_tiles = []
        for defn, rel_x, rel_y, rotation, rel_z in paste_buf:
            new_gx = cx + rel_x
            new_gy = cy + rel_y
            new_tile = PlacedTile(defn, new_gx, new_gy, rotation, rel_z)
            self._model.force_place(new_tile)
            new_tiles.append(new_tile)
        self._view.set_selection(set(new_tiles))
        # Keep paste mode active, preserving any rotation applied since Ctrl+V
        self._view.set_paste_buffer(list(paste_buf))
        self._view.refresh()
        self._mark_dirty()
        self._update_status()

    def _on_selection_rotate(self) -> None:
        self._snapshot()
        selection = list(self._view.selected_tiles())

        # Group centroid (average of each tile's centre)
        group_cx = sum(t.grid_x + t.effective_w / 2.0 for t in selection) / len(selection)
        group_cy = sum(t.grid_y + t.effective_h / 2.0 for t in selection) / len(selection)

        new_tiles = []
        for tile in selection:
            new_rot = (tile.rotation + 90) % 360
            old_ew, old_eh = float(tile.effective_w), float(tile.effective_h)
            new_ew, new_eh = old_eh, old_ew   # dims swap after 90°

            # Rotate this tile's centre 90° CCW around the group centroid
            rx = tile.grid_x + old_ew / 2.0 - group_cx
            ry = tile.grid_y + old_eh / 2.0 - group_cy
            new_tile_cx = group_cx - ry
            new_tile_cy = group_cy + rx

            new_gx = round(new_tile_cx - new_ew / 2.0)
            new_gy = round(new_tile_cy - new_eh / 2.0)
            self._model.remove_tile(tile)
            new_tile = PlacedTile(tile.definition, new_gx, new_gy, new_rot, tile.z_offset)
            self._model.force_place(new_tile)
            new_tiles.append(new_tile)

        self._view.set_selection(set(new_tiles))
        # Snap offsets reference the old tile objects — cancel any in-progress drag
        self._view.cancel_move()
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
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _on_export_assembly_map(self) -> None:
        if not self._model.all_placed():
            QMessageBox.information(self, "Nothing to export",
                                    "Place some tiles first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Assembly Map", "assembly_map.png",
            "PNG image (*.png)")
        if not path:
            return
        title = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
        try:
            png_path = export_assembly_map(self._model, path, title=title)
            QMessageBox.information(
                self, "Exported",
                f"Assembly map saved:\n{png_path}")
        except (OSError, RuntimeError) as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _on_export_assembly_pdf(self) -> None:
        if not self._model.all_placed():
            QMessageBox.information(self, "Nothing to export",
                                    "Place some tiles first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Build Plan", "build_plan.pdf",
            "PDF files (*.pdf)")
        if not path:
            return
        title = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
        try:
            pdf_path = export_assembly_pdf(self._model, path, title=title)
            QMessageBox.information(
                self, "Exported",
                f"Build plan saved:\n{pdf_path}")
        except (OSError, RuntimeError) as exc:
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

    def _on_grid_size(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QWidget

        dlg = QDialog(self)
        dlg.setWindowTitle("Grid Size")
        layout = QFormLayout(dlg)

        def _make_slider_row(current: int):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(1, 200)
            slider.setValue(min(current, 200))
            slider.setFixedWidth(220)

            spin = QSpinBox()
            spin.setRange(1, 9999)
            spin.setValue(current)
            spin.setFixedWidth(75)
            spin.setButtonSymbols(QSpinBox.NoButtons)

            # Slider -> spin: only when user drags, avoids feedback loop
            slider.sliderMoved.connect(spin.setValue)
            # Spin -> slider: clamp to slider range, won't re-trigger sliderMoved
            spin.valueChanged.connect(lambda v: slider.setValue(min(v, 200)))

            h.addWidget(slider)
            h.addWidget(spin)
            return row, spin

        cols_row, cols_spin = _make_slider_row(self._model.GRID_COLS)
        layout.addRow("Columns:", cols_row)

        rows_row, rows_spin = _make_slider_row(self._model.GRID_ROWS)
        layout.addRow("Rows:", rows_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        cols, rows = cols_spin.value(), rows_spin.value()
        if cols == self._model.GRID_COLS and rows == self._model.GRID_ROWS:
            return

        self._snapshot()
        removed = self._model.resize(cols, rows)
        self._view.rebuild_grid_geometry()
        self._mark_dirty()
        self._update_status()

        if removed:
            QMessageBox.warning(
                self, "Tiles removed",
                f"{removed} tile(s) were outside the new grid bounds and have been removed.",
            )

    def _on_camera_speed(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Camera Speed")
        layout = QFormLayout(dlg)

        # Slider: 1–20 maps to speed 0.001–0.020 (stored value × 0.001)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(1, 30)
        slider.setValue(max(1, min(30, round(self._settings.pan_speed * 1000))))
        slider.setFixedWidth(200)
        label = QLabel(f"{self._settings.pan_speed * 1000:.0f}")
        slider.valueChanged.connect(lambda v: label.setText(str(v)))
        layout.addRow("Speed:", slider)
        layout.addRow("Value:", label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        speed = slider.value() * 0.001
        self._settings.pan_speed = speed
        self._settings.save()
        self._view.set_pan_speed(speed)

    def _on_set_ground_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Ground Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)"
        )
        if not path:
            return

        # Use existing rect as default if re-loading the same image,
        # otherwise fit the image's aspect ratio within the grid and center it.
        if self._ground_image and self._ground_image[0] == path:
            default_rect = list(self._ground_image[1])
        else:
            gcols = float(self._model.GRID_COLS)
            grows = float(self._model.GRID_ROWS)
            reader = QImageReader(path)
            sz = reader.size()
            if sz.isValid() and sz.width() > 0 and sz.height() > 0:
                img_aspect = sz.width() / sz.height()
                if img_aspect >= gcols / grows:
                    w, h = gcols, gcols / img_aspect
                else:
                    w, h = grows * img_aspect, grows
            else:
                w, h = gcols, grows
            default_rect = [(gcols - w) / 2, (grows - h) / 2, w, h]

        dlg = QDialog(self)
        dlg.setWindowTitle("Ground Image Size")
        layout = QFormLayout(dlg)

        x_spin = QDoubleSpinBox()
        x_spin.setRange(-400.0, 400.0)
        x_spin.setDecimals(1)
        x_spin.setValue(default_rect[0])
        layout.addRow("X offset (cells):", x_spin)

        y_spin = QDoubleSpinBox()
        y_spin.setRange(-400.0, 400.0)
        y_spin.setDecimals(1)
        y_spin.setValue(default_rect[1])
        layout.addRow("Y offset (cells):", y_spin)

        w_spin = QDoubleSpinBox()
        w_spin.setRange(1.0, 800.0)
        w_spin.setDecimals(1)
        w_spin.setValue(default_rect[2])
        layout.addRow("Width (cells):", w_spin)

        h_spin = QDoubleSpinBox()
        h_spin.setRange(1.0, 800.0)
        h_spin.setDecimals(1)
        h_spin.setValue(default_rect[3])
        layout.addRow("Height (cells):", h_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        self._snapshot()
        rect = [x_spin.value(), y_spin.value(), w_spin.value(), h_spin.value()]
        self._view.set_ground_image(path, rect)
        self._ground_image = (path, rect)
        self._ground_image_aspect = rect[2] / max(rect[3], 1e-6)
        self._show_img_toolbar(rect)
        self._mark_dirty()

    def _on_clear_ground_image(self) -> None:
        if self._ground_image is None:
            return
        self._snapshot()
        self._view.clear_ground_image()
        self._ground_image = None
        self._img_toolbar.hide()
        self._mark_dirty()

    def _on_img_scale_changed(self, value: int) -> None:
        """Scale the ground image around its center when the toolbar slider moves."""
        if not self._ground_image:
            return
        new_w = value / 10.0
        new_h = new_w / max(self._ground_image_aspect, 1e-6)
        rect = self._ground_image[1]
        cx = rect[0] + rect[2] / 2.0
        cy = rect[1] + rect[3] / 2.0
        new_rect = [cx - new_w / 2.0, cy - new_h / 2.0, new_w, new_h]
        self._view.set_ground_image_rect(new_rect)
        self._ground_image = (self._ground_image[0], new_rect)
        self._img_scale_label.setText(f"  {new_w:.1f} cells  ")
        self._mark_dirty()

    def _on_ground_image_moved(self, rect: list) -> None:
        """Receive rect updates from Alt+drag in the GL view."""
        if not self._ground_image:
            return
        self._ground_image = (self._ground_image[0], rect)
        self._img_scale_slider.blockSignals(True)
        self._img_scale_slider.setValue(max(10, int(round(rect[2] * 10))))
        self._img_scale_slider.blockSignals(False)
        self._img_scale_label.setText(f"  {rect[2]:.1f} cells  ")
        self._mark_dirty()

    def _show_img_toolbar(self, rect: list) -> None:
        """Sync the toolbar slider/label to *rect* and show the toolbar."""
        self._img_scale_slider.blockSignals(True)
        self._img_scale_slider.setValue(max(10, int(round(rect[2] * 10))))
        self._img_scale_slider.blockSignals(False)
        self._img_scale_label.setText(f"  {rect[2]:.0f} cells  ")
        self._img_toolbar.show()

    def _apply_theme(self, theme: str) -> None:
        from PySide6.QtWidgets import QApplication
        self._settings.theme = theme
        self._settings.save()
        # Resolve "auto" to the actual system preference
        resolved = self._settings._system_theme() if theme == "auto" else theme
        ss = DARK_STYLESHEET if resolved == "dark" else WIN11_STYLESHEET
        QApplication.instance().setStyleSheet(ss)
        # Tick the correct radio action
        self._act_theme_auto.setChecked(theme == "auto")
        self._act_theme_light.setChecked(theme == "light")
        self._act_theme_dark.setChecked(theme == "dark")
        # Match GL backgrounds
        if resolved == "dark":
            r, g, b   = 0x1F / 255, 0x1F / 255, 0x1F / 255
            ground    = (0.22, 0.22, 0.25)
            grid      = (0.45, 0.45, 0.50)
        else:
            r, g, b   = 0xF3 / 255, 0xF3 / 255, 0xF3 / 255
            ground    = (0.82, 0.82, 0.84)   # slightly darker than void
            grid      = (0.68, 0.68, 0.72)   # visible but soft
        self._view.set_background_color(r, g, b, ground=ground, grid=grid)
        self._palette.set_preview_background(r, g, b)

    def _on_system_theme_changed(self) -> None:
        if self._settings.theme == "auto":
            self._apply_theme("auto")

    def _on_free_mode_changed(self, free: bool) -> None:
        self._free_mode = free
        self._update_status()

    def _update_status(self) -> None:
        name = self._selected_definition.name if self._selected_definition else "None"
        counts = self._model.get_counts()
        total = sum(counts.values())
        counts_str = ", ".join(
            f"{k}: {v}" for k, v in sorted(counts.items())
        ) or "—"
        snap_str = "FREE" if self._free_mode else "SNAP"
        self._status.showMessage(
            f"Selected: {name}  |  Rotation: {self._pending_rotation}°  |  "
            f"Placement: {snap_str}  |  "
            f"Total placed: {total}  |  {counts_str}"
        )
        self._palette.update_info(
            self._pending_rotation,
            counts.get(name, 0) if self._selected_definition else 0,
        )
