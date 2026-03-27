# D&D STL Dungeon Designer

A desktop tool for designing tabletop RPG dungeon layouts by placing modular terrain STL tiles on a grid — like digital Lego. When you're done, export a print list as CSV so you know exactly how many of each tile to print.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![PyQt5](https://img.shields.io/badge/PyQt5-5.15%2B-green) ![OpenGL](https://img.shields.io/badge/OpenGL-4.6%20Core-orange)

![Screenshot](docs/screenshot.png)

---

## Features

- **3D grid layout** — Place modular STL tiles on a snap-to-grid canvas with a live ghost preview and orbit/top-down camera
- **Automatic tile sizing** — Bounding boxes are read directly from each STL file and mapped to grid cells (1 cell = 25 mm); inch-unit files (e.g. OpenForge) are detected and converted automatically
- **Select, move & copy** — Click, rubber-band, or Shift-click to select tiles; drag to reposition, Ctrl+C/V to duplicate
- **Battle map overlay** — Drop any image onto the ground plane and align it to the grid
- **Print list export** — Export a tile-count CSV straight to your slicer queue
- **Assembly map export** — Generate a labeled 2D top-down PNG map and detailed placement CSV showing every tile's position, rotation, and stacking order
- **Combined PDF export** — Export a multi-page PDF with the assembly map on page 1 and a formatted placement table on subsequent pages

---

## Getting Started

### Portable EXE (easiest)

Download `DungeonDesigner.exe` from the [latest release](../../releases/latest) — no Python or dependencies required. Windows may show a SmartScreen warning on first run; click *More info → Run anyway*.

### From source

Requires Python 3.9+ and the following dependencies (installed automatically by `launch.bat`):

```text
PyQt5 >= 5.15
numpy-stl >= 3.0
numpy >= 1.24
PyOpenGL >= 3.1
```

**Windows** — double-click **`launch.bat`**. It will:

1. Create a `.venv` virtual environment if one doesn't exist
2. Install all dependencies into it
3. Launch the application

### Manual

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
python main.py
```

---

## Usage

1. **Load STL folder** — Click *Load STL Folder* in the palette panel and select a directory containing `.stl` files. Each folder opens as a new tab. Load as many folders as you like and switch between them instantly.
2. **Select a tile** — Click a tile in the list. A 3D preview appears below the list; left-drag the preview to orbit it, scroll to zoom.
3. **Place tiles** — Move your mouse over the grid and left-click to place. The ghost preview shows where the tile will land.
4. **Rotate** — Press **R** to rotate the pending tile 90° clockwise. The palette preview updates to match.
5. **Remove** — Right-click a placed tile to remove it.
6. **Select & move placed tiles** — Press **Esc** to deselect any palette tile, then:
   - **Left-click** a tile to select it (highlighted in blue); click elsewhere to deselect.
   - **Shift + left-click** to add or remove tiles from the selection.
   - **Left-drag over empty space** to draw a rubber-band box and select all tiles inside it.
   - **Left-drag a selected tile** to move the entire selection (snaps to grid; hold **Ctrl** for free placement).
   - **R** while dragging rotates the group around its centroid.
   - **Esc** clears the selection.
7. **Copy & paste** — With tiles selected:
   - **Ctrl+C** copies the selection.
   - **Ctrl+V** enters paste ghost mode — semi-transparent ghost tiles follow the cursor. Left-click to place a copy (paste mode stays active for repeated placements). **Esc** exits paste mode.
8. **Navigate the main camera**:
   - **Right-drag** — Orbit (azimuth / elevation)
   - **Middle-drag** — Pan
   - **Scroll wheel** — Zoom in / out
   - **Home** — Reset camera to default position
   - **5** — Toggle top-down orthographic mode (perspective-less overhead view; right-drag and WASD pan, scroll zooms)
9. **Manage folders** — Click the × on a tab to unload that folder. Tiles already placed on the grid remain.
10. **Battle map overlay** — Go to *Edit → Set Ground Image…*, pick an image file, then set its X/Y offset and width/height in grid cells so it lines up with your tile grid. Use *Edit → Clear Ground Image* to remove it.
11. **Export** — Click *Export CSV* to save a print list with tile names and quantities.
12. **Assembly map** — Go to *File → Export Assembly Map…* (Ctrl+Shift+E) to generate a labeled top-down PNG map and a detailed CSV listing every tile placement with its grid position, rotation, and z-offset.
13. **Assembly PDF** — Go to *File → Export Assembly PDF…* (Ctrl+Shift+P) to export a combined PDF with the visual map on page 1 and a formatted placement table on the following pages.

---

## Project Structure

```text
.
├── main.py                  # Entry point, sets up OpenGL surface format
├── launch.bat               # Windows launcher (venv + dependency bootstrap)
├── requirements.txt
├── models/
│   ├── tile_definition.py   # TileDefinition dataclass (name, size, mesh data)
│   ├── placed_tile.py       # PlacedTile (definition + grid position + rotation)
│   └── grid_model.py        # Grid state: placement, collision, counts
├── stl_loader/
│   └── loader.py            # STL parsing, bounding-box sizing, voxel decimation
├── gui/
│   ├── main_window.py         # QMainWindow shell, wires palette ↔ grid view
│   ├── gl_grid_view.py        # QOpenGLWidget: 3D scene, orbit camera, ray-casting
│   ├── tile_preview_widget.py # QOpenGLWidget: isolated 3D preview of selected tile
│   ├── palette_panel.py       # Left panel: folder tabs, tile list, preview, export
│   └── gl_helpers.py          # Shared GLSL shaders + GPU geometry utilities
└── export/
    ├── csv_exporter.py      # CSV print-list export
    └── assembly_map.py      # 2D assembly map PNG + detailed placement CSV
```

---

## Documentation

- [Mesh Processing & LOD](docs/mesh-processing.md) — how STL files are decimated into LOD tiers and how screen-coverage LOD selection works

---

## License

MIT
