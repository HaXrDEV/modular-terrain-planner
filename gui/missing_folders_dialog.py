"""
Dialog shown when a project references folders that no longer exist on disk.
Lets the user remap each missing folder to its new location before the project
finishes loading — tiles from remapped folders are placed normally; anything
still unresolved is reported by filename afterwards.
"""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt


class MissingFoldersDialog(QDialog):
    """
    For each missing folder shows:
      - the original path (read-only, greyed out)
      - an editable line-edit for the replacement path
      - a Browse… button

    Accepting returns a {old_path: new_path} dict for every row where the
    user selected a new folder.  Rows left blank are excluded (skipped).
    """

    def __init__(self, missing_folders: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Missing folders")
        self.setMinimumWidth(640)
        self._rows: dict = {}   # old_path -> QLineEdit

        root = QVBoxLayout(self)
        root.setSpacing(12)

        count = len(missing_folders)
        info = QLabel(
            f"{count} folder{'s' if count != 1 else ''} referenced by this project "
            "could not be found.\n"
            "Browse to the new location for each folder, or leave blank to skip it."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(10)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        for old_path in missing_folders:
            row_widget = QWidget()
            row = QVBoxLayout(row_widget)
            row.setSpacing(2)
            row.setContentsMargins(0, 0, 0, 0)

            old_label = QLabel(old_path)
            old_label.setStyleSheet("color: palette(mid);")
            old_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(old_label)

            picker = QHBoxLayout()
            line = QLineEdit()
            line.setPlaceholderText("Select new folder location…")
            line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            picker.addWidget(line)

            btn = QPushButton("Browse…")
            btn.setFixedWidth(80)
            btn.clicked.connect(lambda _checked, l=line: self._browse(l))
            picker.addWidget(btn)
            row.addLayout(picker)

            inner_layout.addWidget(row_widget)
            self._rows[old_path] = line

        inner_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Load with remapping")
        buttons.button(QDialogButtonBox.Cancel).setText("Skip all")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self, line: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if folder:
            line.setText(folder)

    def remapping(self) -> dict:
        """Return {old_path: new_path} for every row with a non-empty selection."""
        return {
            old: line.text().strip()
            for old, line in self._rows.items()
            if line.text().strip()
        }
