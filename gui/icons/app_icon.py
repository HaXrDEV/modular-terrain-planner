import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG_PATH = os.path.join(os.path.dirname(__file__), "app_icon.svg")


def create_app_icon() -> QIcon:
    with open(_SVG_PATH, "rb") as f:
        renderer = QSvgRenderer(QByteArray(f.read()))

    px = QPixmap(256, 256)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    renderer.render(p, QRectF(0, 0, 256, 256))
    p.end()

    return QIcon(px)
