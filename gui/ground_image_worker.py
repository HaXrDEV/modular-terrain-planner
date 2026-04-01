"""Background worker for loading ground image files off the main thread."""

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage


class GroundImageWorker(QThread):
    """Loads and converts a ground image file in a background thread.

    QImage construction and format conversion are pure data operations that
    do not touch the GUI or the OpenGL context, so they are safe off-thread.
    The raw RGBA pixel bytes are emitted back to the main thread for GPU upload.

    Signals
    -------
    finished(path, width, height, data)
        Emitted with RGBA8888 pixel bytes ready for glTexImage2D.
    failed(path, error_message)
        Emitted if the image could not be loaded.
    """

    finished = pyqtSignal(str, int, int, bytes)   # path, w, h, raw RGBA bytes
    failed   = pyqtSignal(str, str)               # path, error message

    def __init__(self, path: str, parent=None) -> None:
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        img = (
            QImage(self._path)
            .convertToFormat(QImage.Format_RGBA8888)
            .mirrored(False, True)
        )
        if img.isNull():
            self.failed.emit(self._path, "Image could not be loaded")
            return
        ptr = img.bits()
        ptr.setsize(img.byteCount())
        data = bytes(ptr)   # copy before QImage goes out of scope
        self.finished.emit(self._path, img.width(), img.height(), data)
