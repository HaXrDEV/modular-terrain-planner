import sys
import os

# Make sure package root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QSurfaceFormat
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
from gui.style import WIN11_STYLESHEET


def main() -> None:
    # Request desktop OpenGL before QApplication is created (Windows requirement).
    QApplication.setAttribute(Qt.AA_UseDesktopOpenGL)

    # Set OpenGL 3.3 Core as the default format for all GL contexts/widgets.
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)   # 4× MSAA for smooth edges
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("Modular Terrain Planner")

    # Windows 11 system font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    app.setStyleSheet(WIN11_STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
