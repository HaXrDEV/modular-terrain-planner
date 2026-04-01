import sys
import os
import logging
from pathlib import Path

# Make sure package root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

_LOG_DIR  = Path.home() / ".modular-terrain-planner"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8"),
    ],
)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QSurfaceFormat
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
from gui.style import WIN11_STYLESHEET


def main() -> None:
    # Request desktop OpenGL before QApplication is created (Windows requirement).
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)

    # Set OpenGL 4.6 Core as the default format for all GL contexts/widgets.
    fmt = QSurfaceFormat()
    fmt.setVersion(4, 6)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(4)   # 4× MSAA for smooth edges
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("Modular Terrain Planner")

    # Windows 11 system font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Theme is applied inside MainWindow.__init__ from persisted settings.
    # Set light as default so widgets render correctly before the window opens.
    app.setStyleSheet(WIN11_STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
