# Mesh Processing & LOD

STL files for tabletop terrain often contain 100 000–450 000 triangles. The loader builds six LOD levels using **density-based voxel-clustering decimation**, and the renderer selects the right level per tile every frame based on screen coverage.

## Load-time: six LOD tiers

1. The full mesh is loaded and winding is corrected against stored STL normals
2. Actual 3D surface area (in normalised [0,1]³ space) is computed to characterise mesh density
3. Six triangle-count targets are derived from density tiers: `50 000 → 20 000 → 8 000 → 4 000 → 2 500 → 1 500` triangles per surface-area unit
4. For each target, **vertex-clustering decimation** (`_decimate`) merges vertices that fall in the same cell of a *grid*³ lattice and discards degenerate triangles — the surface stays watertight
5. A mesh is only decimated for a given tier if its original density is at least **5×** the tier's target — low-quality meshes fall back to their full resolution rather than degrading further
6. Triangle counts per level are stored alongside each mesh for fast LOD selection at draw time

## Draw-time: screen-coverage LOD selection

Rather than using camera distance, LOD is chosen per tile based on the tile's **projected pixel area**:

1. The 8 corners of each tile's axis-aligned bounding box are projected to NDC in a single vectorised numpy pass
2. Pixel area = `NDC span X × viewport width/2 × NDC span Y × viewport height/2`
3. Triangle target = `pixel_area × 2.0` (two triangles per pixel)
4. The LOD tier whose actual triangle count is closest to the target is selected

Large tiles close to the camera stay fully detailed; the same tile viewed from far away or at a glancing angle drops to the coarsest tier automatically. The full-resolution mesh is never uploaded — only the selected LOD level is sent to the GPU each frame.

Flat per-face normals are computed from the cross product of each triangle's edges, so shading works correctly regardless of the normals stored in the STL file.

## Selection outline

The selection highlight uses a 3-pass screen-space stencil dilation rather than back-face extrusion, which correctly outlines concave models such as doorways and arches:

1. **Pass 1** — the tile mesh is drawn 8 times with small NDC-space offsets (cardinal + diagonal directions) → `stencil = 1` over the full dilated silhouette
2. **Pass 2** — the tile mesh is drawn at the exact position → `stencil = 2` clears the interior, leaving `stencil = 1` only on the border ring
3. **Pass 3** — a fullscreen quad coloured #0078D4 is drawn where `stencil == 1` → paints only the border, never the tile surface itself

The NDC offset trick (`pos.xy += uNDCOffset * pos.w` in the vertex shader) keeps outline thickness fixed in pixels regardless of tile size or camera distance.
