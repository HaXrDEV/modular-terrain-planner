"""Background worker for loading STL folders off the main thread."""

from typing import List

from PyQt5.QtCore import QThread, pyqtSignal

from models.tile_definition import TileDefinition
from stl_loader.loader import load_stl_folder


class STLLoaderWorker(QThread):
    """Loads an STL folder in a background thread.

    Signals
    -------
    finished(folder, definitions)
        Emitted when loading completes successfully.
    failed(folder, error_message)
        Emitted when loading fails or finds no STL files.
    """

    finished = pyqtSignal(str, list)   # (folder_path, List[TileDefinition])
    failed   = pyqtSignal(str, str)    # (folder_path, error_message)

    def __init__(self, folder: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder

    def run(self) -> None:
        try:
            definitions = load_stl_folder(self._folder)
        except Exception as exc:
            self.failed.emit(self._folder, str(exc))
            return
        if not definitions:
            self.failed.emit(self._folder, "No .stl files found")
            return
        self.finished.emit(self._folder, definitions)
