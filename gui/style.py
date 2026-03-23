"""
Windows 11-inspired light-mode stylesheet for Modular Terrain Planner.

Colour palette mirrors the Win11 Settings / File Explorer aesthetic:
  - Base surface    #f3f3f3  (window / panel backgrounds)
  - Card surface    #ffffff  (list / input backgrounds)
  - Sidebar surface #ebebeb  (palette panel)
  - Divider         #e0e0e0
  - Text primary    #1a1a1a
  - Text secondary  #5a5a5a
  - Accent          #0067c0  (Windows default blue)
  - Accent hover    #1a78c9
  - Accent pressed  #005499
  - Selection bg    #cce4f7
  - Button bg       #fbfbfb
  - Button hover    #f0f0f0
  - Button pressed  #e5e5e5
"""
import os as _os

_ICONS = _os.path.join(_os.path.dirname(__file__), "icons").replace("\\", "/")

WIN11_STYLESHEET = f"""
/* ── Global ─────────────────────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 9pt;
    color: #1a1a1a;
}}

QMainWindow, QDialog {{
    background: #f3f3f3;
}}

QWidget {{
    background: #f3f3f3;
}}

/* ── Splitter ────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: #e0e0e0;
    width: 1px;
    height: 1px;
}}

/* ── Menu bar ────────────────────────────────────────────────────────── */
QMenuBar {{
    background: #f3f3f3;
    border-bottom: 1px solid #e0e0e0;
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected,
QMenuBar::item:pressed {{
    background: #e5e5e5;
}}

QMenu {{
    background: #ffffff;
    border: 1px solid #e0e0e0;
    padding: 4px 0px;
}}
QMenu::item {{
    padding: 6px 28px 6px 24px;
    border-radius: 4px;
    margin: 1px 4px;
}}
QMenu::item:selected {{
    background: #cce4f7;
    color: #003d73;
}}
QMenu::item:disabled {{
    color: #aaaaaa;
}}
QMenu::separator {{
    height: 1px;
    background: #e0e0e0;
    margin: 4px 10px;
}}

/* ── Toolbar ─────────────────────────────────────────────────────────── */
QToolBar {{
    background: #f3f3f3;
    border-bottom: 1px solid #e0e0e0;
    padding: 3px 6px;
    spacing: 4px;
}}

/* ── Status bar ──────────────────────────────────────────────────────── */
QStatusBar {{
    background: #f3f3f3;
    border-top: 1px solid #e0e0e0;
    color: #5a5a5a;
    font-size: 8pt;
    padding: 2px 6px;
}}

/* ── Push buttons ────────────────────────────────────────────────────── */
QPushButton {{
    background: #fbfbfb;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 5px 16px;
    min-height: 22px;
}}
QPushButton:hover {{
    background: #f0f0f0;
    border-color: #bdbdbd;
}}
QPushButton:pressed {{
    background: #e5e5e5;
    border-color: #b0b0b0;
}}
QPushButton:disabled {{
    background: #f3f3f3;
    border-color: #dddddd;
    color: #aaaaaa;
}}
QPushButton:default {{
    background: #0067c0;
    border: 1px solid #005499;
    color: #ffffff;
}}
QPushButton:default:hover {{
    background: #1a78c9;
}}
QPushButton:default:pressed {{
    background: #005499;
}}

/* ── Tab widget ──────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-top: none;
    border-radius: 0px 0px 4px 4px;
}}

QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    margin-right: 2px;
    color: #5a5a5a;
    min-width: 60px;
}}
QTabBar::tab:selected {{
    color: #1a1a1a;
    border-bottom: 2px solid #0067c0;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    color: #1a1a1a;
    border-bottom: 2px solid #bdbdbd;
}}
QTabBar::close-button {{
    image: url("{_ICONS}/tab_close.svg");
    subcontrol-position: right;
    width: 14px;
    height: 14px;
    border-radius: 3px;
    margin-left: 4px;
}}
QTabBar::close-button:hover {{
    image: url("{_ICONS}/tab_close_hover.svg");
    background: #d9d9d9;
}}

/* ── List widget ─────────────────────────────────────────────────────── */
QListWidget {{
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    outline: none;
    padding: 2px;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background: #f0f6fd;
}}
QListWidget::item:selected {{
    background: #cce4f7;
    color: #003d73;
}}

/* ── Scroll bars ─────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #c8c8c8;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #a8a8a8;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: #c8c8c8;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #a8a8a8;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0px;
}}

/* ── Spin boxes / line edits ─────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: #ffffff;
    border: 1px solid #cccccc;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    selection-background-color: #cce4f7;
}}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1px solid #0067c0;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    border-left: 1px solid #e0e0e0;
    border-radius: 0px 4px 4px 0px;
    background: #f3f3f3;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #e5e5e5;
}}

/* ── Slider ──────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: #e0e0e0;
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #0067c0;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #1a78c9;
}}
QSlider::sub-page:horizontal {{
    background: #0067c0;
    border-radius: 2px;
}}

/* ── Dialog buttons ──────────────────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* ── Labels ──────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: #1a1a1a;
}}

/* ── Form layout label column ────────────────────────────────────────── */
QFormLayout QLabel {{
    color: #5a5a5a;
    font-size: 9pt;
}}

/* ── Tooltip ─────────────────────────────────────────────────────────── */
QToolTip {{
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1a1a1a;
    font-size: 8pt;
}}

/* ── Palette sidebar (fixed-width left panel) ────────────────────────── */
PalettePanel {{
    background: #ebebeb;
    border-right: 1px solid #e0e0e0;
}}
PalettePanel QTabWidget::pane {{
    background: #ffffff;
}}
"""
