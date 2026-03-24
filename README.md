# D&D STL Dungeon Designer

A desktop tool for designing tabletop RPG dungeon layouts by placing modular terrain STL tiles on a grid — like digital Lego. When you're done, export a print list as CSV so you know exactly how many of each tile to print.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![PyQt5](https://img.shields.io/badge/PyQt5-5.15%2B-green) ![OpenGL](https://img.shields.io/badge/OpenGL-4.6%20Core-orange)

![Screenshot](docs/screenshot.png)

---

## Features

- **3D dungeon view** — Full OpenGL 4.6 rendering with flat shading and three-point lighting
- **Interactive orbit camera** — Rotate, pan, and zoom around the dungeon layout
- **Tile model previewer** — 3D preview of the selected tile in the palette; orbit and zoom independently
- **Multi-folder tabs** — Load multiple STL folders as separate tabs and switch between them instantly
- **Auto-detect tile size** — Reads bounding boxes from STL files and maps them to grid cells (1 cell = 25 mm)
- **Snap-to-grid placement** — Left-click to place, right-click to remove; pending tile centers on cursor
- **Ghost preview** — Hover to see where a tile will land before placing it
- **Tile rotation** — Press R to rotate the pending tile 90°; rotation pivots around the cursor
- **Select & move** — When no tile is selected in the palette, left-click/drag to select placed tiles and reposition them; Shift-click to add to the selection; drag a box over empty space for rubber-band multi-select
- **Battle map overlay** — Load any image (PNG/JPG/BMP) as a ground-plane texture; position and scale it to match the grid
- **Print list export** — Export tile counts to CSV for your slicer/print queue
- **Inches heuristic** — Automatically detects and converts inch-unit STL files (e.g. OpenForge tiles)

---

## Requirements

- Python 3.9 or newer
- Windows (tested), should work on Linux/macOS with minor path adjustments

Dependencies are installed automatically by `launch.bat`:

```
PyQt5 >= 5.15
numpy-stl >= 3.0
numpy >= 1.24
PyOpenGL >= 3.1
```

---

## Getting Started

### Windows (recommended)

Double-click **`launch.bat`**. It will:
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
9. **Manage folders** — Click the × on a tab to unload that folder. Tiles already placed on the grid remain.
10. **Battle map overlay** — Go to *Edit → Set Ground Image…*, pick an image file, then set its X/Y offset and width/height in grid cells so it lines up with your tile grid. Use *Edit → Clear Ground Image* to remove it.
11. **Export** — Click *Export CSV* to save a print list with tile names and quantities.

---

## Project Structure

```
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
    └── csv_exporter.py      # CSV print-list export
```

---

## Mesh Processing & LOD

STL files for tabletop terrain often contain 100 000–450 000 triangles. The loader builds six LOD levels using **density-based voxel-clustering decimation**, and the renderer selects the right level per tile every frame based on screen coverage.

### Load-time: six LOD tiers

1. The full mesh is loaded and winding is corrected against stored STL normals
2. Actual 3D surface area (in normalised [0,1]³ space) is computed to characterise mesh density
3. Six triangle-count targets are derived from density tiers: `50 000 → 20 000 → 8 000 → 3 000 → 800 → 150` triangles per surface-area unit
4. For each target, **vertex-clustering decimation** (`_decimate`) merges vertices that fall in the same cell of a *grid*³ lattice and discards degenerate triangles — the surface stays watertight
5. Sparse meshes (density < 500 tri/unit²) skip decimation entirely — they are already low-poly
6. Triangle counts per level are stored alongside each mesh for fast LOD selection at draw time

### Draw-time: screen-coverage LOD selection

Rather than using camera distance, LOD is chosen per tile based on the tile's **projected pixel area**:

1. The 8 corners of each tile's axis-aligned bounding box are projected to NDC in a single vectorised numpy pass
2. Pixel area = `NDC span X × viewport width/2 × NDC span Y × viewport height/2`
3. Triangle target = `pixel_area × 0.5` (half a triangle per pixel)
4. The LOD tier whose actual triangle count is closest to the target is selected

Large tiles close to the camera stay fully detailed; the same tile viewed from far away or at a glancing angle drops to the coarsest tier automatically. The full-resolution mesh is never uploaded — only the selected LOD level is sent to the GPU each frame.

Flat per-face normals are computed from the cross product of each triangle's edges, so shading works correctly regardless of the normals stored in the STL file.

---

## License

MIT
