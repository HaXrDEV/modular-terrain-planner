import sys
import os

# Make sure package root is on the path when running directly
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("D&D STL Dungeon Designer")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
