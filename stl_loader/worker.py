"""Background worker for loading STL folders off the main thread."""

from typing import List

from PySide6.QtCore import QThread, Signal

from models.tile_definition import TileDefinition
from stl_loader.loader import load_stl_folder


class STLLoaderWorker(QThread):
    """Loads an STL folder in a background thread.

    Signals
    -------
    finished(folder, definitions, errors)
        Emitted when loading completes (possibly with some files skipped).
    failed(folder, error_message)
        Emitted when loading fails entirely or finds no STL files.
    """

    finished = Signal(str, list, list)  # (folder_path, definitions, errors)
    failed   = Signal(str, str)         # (folder_path, error_message)

    def __init__(self, folder: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder

    def run(self) -> None:
        try:
            errors: List[str] = []
            definitions = load_stl_folder(self._folder, errors=errors)
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(self._folder, str(exc))
            return
        if not definitions:
            self.failed.emit(self._folder, "No .stl files found")
            return
        self.finished.emit(self._folder, definitions, errors)
