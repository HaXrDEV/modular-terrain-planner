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
    progress(current, total)
        Emitted after each file is processed. current=0 is the initial call
        before any file is processed, so callers can initialise the range.
    """

    finished = Signal(str, list, list)  # (folder_path, definitions, errors)
    failed   = Signal(str, str)         # (folder_path, error_message)
    progress = Signal(int, int)         # (current, total)

    def __init__(self, folder: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. The worker will stop after the current file."""
        self._cancelled = True

    def _progress_cb(self, current: int, total: int) -> None:
        self.progress.emit(current, total)
        if self._cancelled:
            raise InterruptedError("Cancelled by user")

    def run(self) -> None:
        try:
            errors: List[str] = []
            definitions = load_stl_folder(self._folder, errors=errors,
                                          progress_cb=self._progress_cb)
        except InterruptedError:
            self.failed.emit(self._folder, "Cancelled")
            return
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(self._folder, str(exc))
            return
        if not definitions:
            self.failed.emit(self._folder, "No .stl files found")
            return
        self.finished.emit(self._folder, definitions, errors)
