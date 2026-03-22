import os
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QLabel, QSizePolicy, QTabWidget,
)

from models.tile_definition import TileDefinition
from gui.tile_preview_widget import TilePreviewWidget


class PalettePanel(QWidget):
    tile_selected       = pyqtSignal(object)   # emits TileDefinition | None
    load_folder_clicked = pyqtSignal()
    export_clicked      = pyqtSignal()
    tab_closed          = pyqtSignal(str)       # emits folder path

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(240)
        self._selected: Optional[TileDefinition] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._load_btn = QPushButton("Load STL Folder")
        self._load_btn.clicked.connect(self.load_folder_clicked)
        layout.addWidget(self._load_btn)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabBar().setUsesScrollButtons(True)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, stretch=1)

        self._preview = TilePreviewWidget()
        layout.addWidget(self._preview)

        self._info_label = QLabel("No tile selected")
        self._info_label.setWordWrap(True)
        self._info_label.setFixedHeight(52)
        layout.addWidget(self._info_label)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.clicked.connect(self.export_clicked)
        layout.addWidget(self._export_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_folder_tab(self, folder: str, definitions: List[TileDefinition]) -> None:
        """Create a new tab for *folder* and populate it with *definitions*."""
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        lst = QListWidget()
        lst.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for defn in definitions:
            item = QListWidgetItem(
                _color_icon(defn.color),
                f"{defn.name}  ({defn.grid_w}×{defn.grid_h})",
            )
            item.setData(Qt.UserRole, defn)
            lst.addItem(item)
        lst.currentItemChanged.connect(self._on_selection_changed)
        page_layout.addWidget(lst)

        basename = os.path.basename(folder.rstrip('/\\'))
        label = ('…' + basename[-15:]) if len(basename) > 16 else basename
        idx = self._tabs.addTab(page, label)
        self._tabs.tabBar().setTabData(idx, folder)
        self._tabs.setTabToolTip(idx, folder)
        self._tabs.setCurrentIndex(idx)

    def focus_folder_tab(self, folder: str) -> None:
        """Switch to the tab whose data matches *folder*."""
        for i in range(self._tabs.count()):
            if self._tabs.tabBar().tabData(i) == folder:
                self._tabs.setCurrentIndex(i)
                return

    def selected_definition(self) -> Optional[TileDefinition]:
        return self._selected

    def update_info(self, rotation: int, count: int) -> None:
        if self._selected:
            self._info_label.setText(
                f"<b>{self._selected.name}</b><br>"
                f"Size: {self._selected.grid_w}×{self._selected.grid_h} cells<br>"
                f"Rotation: {rotation}°  |  Placed: {count}"
            )
            self._preview.set_tile(self._selected, rotation)
        else:
            self._info_label.setText("No tile selected")
            self._preview.set_tile(None)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        self._selected = current.data(Qt.UserRole) if current is not None else None
        self._preview.set_tile(self._selected, 0)
        self.tile_selected.emit(self._selected)

    def _on_tab_changed(self, index: int) -> None:
        # Clear selection when switching between folder tabs
        self._selected = None
        self._preview.set_tile(None)
        self.tile_selected.emit(None)

        if index >= 0:
            page = self._tabs.widget(index)
            if page is not None:
                lst = page.findChild(QListWidget)
                if lst is not None:
                    lst.clearSelection()

    def _on_tab_close_requested(self, index: int) -> None:
        folder_path = self._tabs.tabBar().tabData(index)
        self._tabs.removeTab(index)
        if self._tabs.count() == 0:
            self._selected = None
            self._preview.set_tile(None)
            self._info_label.setText("No tile selected")
            self.tile_selected.emit(None)
        if folder_path:
            self.tab_closed.emit(folder_path)


def _color_icon(color: QColor, size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(color)
    return QIcon(pix)
