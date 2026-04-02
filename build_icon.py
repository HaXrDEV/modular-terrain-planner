"""
Generates gui/icons/app_icon.ico for use with PyInstaller's --icon flag.
Requires PySide6 (already a project dependency) and Pillow.
Run from the project root before building the EXE.
"""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODeviceBase
from PySide6.QtWidgets import QApplication
from PIL import Image

app = QApplication(sys.argv)

from gui.icons.app_icon import create_app_icon

icon = create_app_icon()
images = []

for size in [16, 32, 48, 256]:
    px = icon.pixmap(size, size)
    buf = QBuffer()
    buf.open(QIODeviceBase.OpenModeFlag.WriteOnly)
    px.save(buf, "PNG")
    buf.close()
    images.append(Image.open(io.BytesIO(bytes(buf.data()))))

out_path = os.path.join("gui", "icons", "app_icon.ico")
images[0].save(
    out_path,
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    append_images=images[1:],
)
print(f"Generated {out_path}")
