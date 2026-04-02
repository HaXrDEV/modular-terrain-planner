"""
Stylesheets for Modular Terrain Planner.

WIN11_STYLESHEET  — Windows 11 light-mode (default)
DARK_STYLESHEET   — Dark mode theme

Light palette:
  - Base surface    #f3f3f3
  - Card surface    #ffffff
  - Sidebar surface #ebebeb
  - Divider         #e0e0e0
  - Text primary    #1a1a1a  /  secondary #5a5a5a
  - Accent          #0067c0

Dark palette:
  - Window bg       #1F1F1F
  - Sidebar bg      #181818
  - Surface/input   #313131
  - Border          #2B2B2B
  - Text primary    #CCCCCC  /  secondary #9D9D9D
  - Accent          #0078D4
  - Selection bg    #0078D4
  - List hover      #2A2D2E
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
QTabBar QToolButton#tabCloseBtn {{
    background: transparent;
    border: none;
    border-radius: 3px;
    color: #7a7a7a;
    font-size: 9pt;
    padding: 0px;
    margin: 0px;
}}
QTabBar QToolButton#tabCloseBtn:hover {{
    background: #d9d9d9;
    color: #1a1a1a;
}}

/* Tab bar scroll arrows (shown when tabs overflow) */
QTabBar QToolButton {{
    background: #f3f3f3;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 2px;
    margin: 2px 1px;
}}
QTabBar QToolButton:hover {{
    background: #e5e5e5;
    border-color: #bdbdbd;
}}
QTabBar QToolButton:pressed {{
    background: #d9d9d9;
}}
QTabBar QToolButton:disabled {{
    background: transparent;
    border-color: transparent;
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

# ---------------------------------------------------------------------------
# Dark theme
# ---------------------------------------------------------------------------
DARK_STYLESHEET = f"""
/* ── Global ─────────────────────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 9pt;
    color: #CCCCCC;
}}

QMainWindow, QDialog {{
    background: #1F1F1F;
}}

QWidget {{
    background: #1F1F1F;
}}

/* ── Splitter ────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: #2B2B2B;
    width: 1px;
    height: 1px;
}}

/* ── Menu bar  (titleBar.activeBackground / titleBar.border) ─────────── */
QMenuBar {{
    background: #181818;
    border-bottom: 1px solid #2B2B2B;
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected,
QMenuBar::item:pressed {{
    background: #2B2B2B;
}}

/* menu.background / widget.border / menu.selectionBackground */
QMenu {{
    background: #1F1F1F;
    border: 1px solid #313131;
    padding: 4px 0px;
}}
QMenu::item {{
    padding: 6px 28px 6px 24px;
    border-radius: 4px;
    margin: 1px 4px;
    color: #CCCCCC;
}}
QMenu::item:selected {{
    background: #0078D4;
    color: #FFFFFF;
}}
QMenu::item:disabled {{
    color: #6E7681;
}}
QMenu::separator {{
    height: 1px;
    background: #2B2B2B;
    margin: 4px 10px;
}}

/* ── Toolbar  (panel.background / panel.border) ──────────────────────── */
QToolBar {{
    background: #181818;
    border-bottom: 1px solid #2B2B2B;
    padding: 3px 6px;
    spacing: 4px;
}}

/* ── Status bar  (statusBar.*) ───────────────────────────────────────── */
QStatusBar {{
    background: #181818;
    border-top: 1px solid #2B2B2B;
    color: #CCCCCC;
    font-size: 8pt;
    padding: 2px 6px;
}}

/* ── Push buttons
       primary (default): button.background / button.hoverBackground
       regular:           button.secondaryBackground (#313131 stand-in)  */
QPushButton {{
    background: #313131;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 5px 16px;
    min-height: 22px;
    color: #CCCCCC;
}}
QPushButton:hover {{
    background: #3C3C3C;
    border-color: #4E4E4E;
}}
QPushButton:pressed {{
    background: #2B2B2B;
    border-color: #3C3C3C;
}}
QPushButton:disabled {{
    background: #252525;
    border-color: #2B2B2B;
    color: #6E7681;
}}
QPushButton:default {{
    background: #0078D4;
    border: 1px solid #0078D4;
    color: #FFFFFF;
}}
QPushButton:default:hover {{
    background: #026EC1;
    border-color: #026EC1;
}}
QPushButton:default:pressed {{
    background: #005FAD;
}}

/* ── Tab widget
       pane:   editor.background / tab.border
       tabbar: editorGroupHeader.tabsBackground
       tab:    tab.inactiveBackground / tab.inactiveForeground
       active: tab.activeBackground / tab.activeBorderTop / tab.activeForeground
       hover:  tab.hoverBackground                                        */
QTabWidget::pane {{
    background: #1F1F1F;
    border: 1px solid #2B2B2B;
    border-top: none;
}}

QTabBar {{
    background: #181818;
}}
QTabBar::tab {{
    background: #181818;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    margin-right: 1px;
    color: #9D9D9D;
    min-width: 60px;
}}
QTabBar::tab:selected {{
    background: #1F1F1F;
    color: #FFFFFF;
    border-bottom: 2px solid #0078D4;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: #1F1F1F;
    color: #CCCCCC;
    border-bottom: 2px solid #2B2B2B;
}}
QTabBar QToolButton#tabCloseBtn {{
    background: transparent;
    border: none;
    border-radius: 3px;
    color: #9D9D9D;
    font-size: 9pt;
    padding: 0px;
    margin: 0px;
}}
QTabBar QToolButton#tabCloseBtn:hover {{
    background: #3C3C3C;
    color: #CCCCCC;
}}

/* Tab bar scroll arrows */
QTabBar QToolButton {{
    background: #181818;
    border: 1px solid #2B2B2B;
    border-radius: 4px;
    padding: 2px;
    margin: 2px 1px;
    color: #CCCCCC;
}}
QTabBar QToolButton:hover {{
    background: #2B2B2B;
    border-color: #3C3C3C;
}}
QTabBar QToolButton:pressed {{
    background: #1F1F1F;
}}
QTabBar QToolButton:disabled {{
    background: transparent;
    border-color: transparent;
}}

/* ── List widget  (sideBar.background / menu.selectionBackground) ────── */
QListWidget {{
    background: #1F1F1F;
    border: 1px solid #2B2B2B;
    border-radius: 4px;
    outline: none;
    padding: 2px;
}}
QListWidget::item {{
    padding: 5px 8px;
    border-radius: 4px;
    color: #CCCCCC;
}}
QListWidget::item:hover {{
    background: #2A2D2E;
}}
QListWidget::item:selected {{
    background: #0078D4;
    color: #FFFFFF;
}}

/* ── Scroll bars  (badge.background = #616161) ───────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #424242;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #616161;
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
    background: #424242;
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #616161;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    width: 0px;
}}

/* ── Inputs  (input.background / input.border / focusBorder) ─────────── */
QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: #313131;
    border: 1px solid #3C3C3C;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    color: #CCCCCC;
    selection-background-color: #0078D4;
}}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1px solid #0078D4;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    border-left: 1px solid #3C3C3C;
    border-radius: 0px 4px 4px 0px;
    background: #2B2B2B;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #3C3C3C;
}}

/* ── Slider  (progressBar.background / focusBorder = #0078D4) ────────── */
QSlider::groove:horizontal {{
    background: #3C3C3C;
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #0078D4;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: #026EC1;
}}
QSlider::sub-page:horizontal {{
    background: #0078D4;
    border-radius: 2px;
}}

/* ── Dialog buttons ──────────────────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* ── Labels ──────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: #CCCCCC;
}}

QFormLayout QLabel {{
    color: #9D9D9D;
    font-size: 9pt;
}}

/* ── Tooltip  (editorWidget.background / widget.border) ─────────────── */
QToolTip {{
    background: #202020;
    border: 1px solid #313131;
    padding: 4px 8px;
    color: #CCCCCC;
    font-size: 8pt;
}}

/* ── Palette sidebar  (sideBar.background / sideBar.border) ─────────── */
PalettePanel {{
    background: #181818;
    border-right: 1px solid #2B2B2B;
}}
PalettePanel QTabWidget::pane {{
    background: #1F1F1F;
}}
"""
