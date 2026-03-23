import math
import os
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImageReader
from PyQt5.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QStatusBar,
    QAction, QMenuBar, QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
    QDoubleSpinBox, QToolBar, QSlider, QLabel,
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

        # Undo / redo stacks — each entry is a state snapshot dict
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        _MAX_UNDO = 100

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
        self._palette.export_clicked.connect(self._on_export_csv)
        self._palette.tab_closed.connect(self._on_tab_closed)

        self._view.tile_place_requested.connect(self._on_tile_placed)
        self._view.tile_remove_requested.connect(self._on_tile_removed)
        self._view.rotate_requested.connect(self._on_rotate)
        self._view.deselect_requested.connect(self._on_deselect)
        self._view.ground_image_rect_changed.connect(self._on_ground_image_moved)

        self._img_scale_slider.valueChanged.connect(self._on_img_scale_changed)

        self._view.set_pan_speed(self._settings.pan_speed)

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

    def _apply_project(self, folders: list, tile_records: list,
                       grid_cols: int = 40, grid_rows: int = 40,
                       ground_image=None) -> None:
        """
        Clear the current session and apply a loaded project.
        Missing folders or unresolvable stl_paths are skipped with a warning.
        """
        self._on_new(confirm=False)
        self._model.GRID_COLS = grid_cols
        self._model.GRID_ROWS = grid_rows
        self._view.rebuild_grid_geometry()

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
                z_offset=rec["z_offset"],
            )
            self._model.place(pt)

        self._view.refresh()
        self._update_status()

        # Restore ground image
        if ground_image and os.path.isfile(ground_image["path"]):
            rect = ground_image["rect"]
            self._view.set_ground_image(ground_image["path"], rect)
            self._ground_image = (ground_image["path"], rect)
            self._ground_image_aspect = rect[2] / max(rect[3], 1e-6)
            self._show_img_toolbar(rect)
        else:
            self._ground_image = None
            self._img_toolbar.hide()

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

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------

    def _snapshot(self) -> None:
        """Push the current state onto the undo stack and clear redo."""
        snap = {
            "tiles": [
                (pt.definition, pt.grid_x, pt.grid_y, pt.rotation, pt.z_offset)
                for pt in self._model.all_placed()
            ],
            "ground_image": self._ground_image,
            "grid_cols": self._model.GRID_COLS,
            "grid_rows": self._model.GRID_ROWS,
        }
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_actions()

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
        # Save current state for redo
        current = {
            "tiles": [
                (pt.definition, pt.grid_x, pt.grid_y, pt.rotation, pt.z_offset)
                for pt in self._model.all_placed()
            ],
            "ground_image": self._ground_image,
            "grid_cols": self._model.GRID_COLS,
            "grid_rows": self._model.GRID_ROWS,
        }
        self._redo_stack.append(current)
        self._restore(self._undo_stack.pop())
        self._update_undo_actions()

    def _on_redo(self) -> None:
        if not self._redo_stack:
            return
        current = {
            "tiles": [
                (pt.definition, pt.grid_x, pt.grid_y, pt.rotation, pt.z_offset)
                for pt in self._model.all_placed()
            ],
            "ground_image": self._ground_image,
            "grid_cols": self._model.GRID_COLS,
            "grid_rows": self._model.GRID_ROWS,
        }
        self._undo_stack.append(current)
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
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._apply_project(folders, tile_records, grid_cols, grid_rows, ground_image)
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
            save_project(path, folders, self._model.all_placed(),
                         self._model.GRID_COLS, self._model.GRID_ROWS,
                         self._ground_image)
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

    def _on_tile_placed(self, gx: float, gy: float) -> None:
        if self._selected_definition is None:
            return
        self._snapshot()
        from PyQt5.QtWidgets import QApplication
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

    def _on_tile_removed(self, gx: int, gy: int) -> None:
        self._snapshot()
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

    def _on_grid_size(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Grid Size")
        layout = QFormLayout(dlg)

        cols_spin = QSpinBox()
        cols_spin.setRange(1, 200)
        cols_spin.setValue(self._model.GRID_COLS)
        layout.addRow("Columns:", cols_spin)

        rows_spin = QSpinBox()
        rows_spin.setRange(1, 200)
        rows_spin.setValue(self._model.GRID_ROWS)
        layout.addRow("Rows:", rows_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addRow(buttons)

        if dlg.exec_() != QDialog.Accepted:
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

        if dlg.exec_() != QDialog.Accepted:
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

        if dlg.exec_() != QDialog.Accepted:
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
