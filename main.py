import sys
import os

# Make sure package root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow


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
    app.setApplicationName("D&D STL Dungeon Designer")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
