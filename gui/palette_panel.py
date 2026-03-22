from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QSizePolicy,
)

from models.tile_definition import TileDefinition


class PalettePanel(QWidget):
    tile_selected = pyqtSignal(object)   # emits TileDefinition | None
    load_folder_clicked = pyqtSignal()
    export_clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(240)
        self._definitions: List[TileDefinition] = []
        self._selected: Optional[TileDefinition] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._load_btn = QPushButton("Load STL Folder")
        self._load_btn.clicked.connect(self.load_folder_clicked)
        layout.addWidget(self._load_btn)

        layout.addWidget(QLabel("Tiles:"))

        self._list = QListWidget()
        self._list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        self._info_label = QLabel("No tile selected")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.clicked.connect(self.export_clicked)
        layout.addWidget(self._export_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def populate(self, definitions: List[TileDefinition]) -> None:
        self._definitions = definitions
        self._list.clear()
        for defn in definitions:
            item = QListWidgetItem(_color_icon(defn.color), f"{defn.name}  ({defn.grid_w}×{defn.grid_h})")
            item.setData(Qt.UserRole, defn)
            self._list.addItem(item)

    def selected_definition(self) -> Optional[TileDefinition]:
        return self._selected

    def update_info(self, rotation: int, count: int) -> None:
        if self._selected:
            self._info_label.setText(
                f"<b>{self._selected.name}</b><br>"
                f"Size: {self._selected.grid_w}×{self._selected.grid_h} cells<br>"
                f"Rotation: {rotation}°<br>"
                f"Placed: {count}"
            )
        else:
            self._info_label.setText("No tile selected")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            self._selected = None
        else:
            self._selected = current.data(Qt.UserRole)
        self.tile_selected.emit(self._selected)


def _color_icon(color: QColor, size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(color)
    return QIcon(pix)
