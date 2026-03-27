"""Export assembly map (PNG), detailed placement CSV, and combined PDF."""

import csv
import math
import os
from typing import TYPE_CHECKING, List, Tuple

from PyQt5.QtCore import Qt, QRect, QRectF, QPointF, QMarginsF, QSizeF
from PyQt5.QtGui import (
    QImage, QPainter, QColor, QFont, QPen, QBrush, QPolygonF, QFontMetrics,
    QPageLayout, QPageSize,
)

if TYPE_CHECKING:
    from models.grid_model import GridModel
    from models.placed_tile import PlacedTile

# ---------------------------------------------------------------------------
# Layout constants (pixels)
# ---------------------------------------------------------------------------
_BASE_CELL_PX = 40
_MARGIN_PX = 50
_LEGEND_W_PX = 300
_TITLE_H_PX = 44
_MAX_LEGEND_ENTRIES = 50

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contrast_color(bg: QColor) -> QColor:
    """Return black or white depending on background luminance."""
    lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    return QColor(Qt.black) if lum > 128 else QColor(Qt.white)


def _darker_border(color: QColor) -> QColor:
    """Return a darker shade for tile borders."""
    h, s, v, a = color.getHsv()
    return QColor.fromHsv(h, min(s + 30, 255), max(v - 60, 0), a)


def _cell_px(grid_cols: int, grid_rows: int) -> int:
    """Adapt cell size so the image stays reasonable for large grids."""
    longest = max(grid_cols, grid_rows)
    if longest <= 120:
        return _BASE_CELL_PX
    return max(20, 4800 // longest)


def _axis_step(cells: int) -> int:
    """Label every Nth axis tick so labels don't overlap."""
    if cells <= 30:
        return 1
    if cells <= 80:
        return 5
    return 10


def _draw_outlined_text(
    p: QPainter, x: float, y: float, text: str,
    fg: QColor, outline: QColor, flags: int = Qt.AlignCenter,
    rect: QRectF = None,
) -> None:
    """Draw *text* with a 1-px outline for readability on any background."""
    p.setPen(QPen(outline))
    if rect is not None:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(rect.adjusted(dx, dy, dx, dy), flags, text)
        p.setPen(QPen(fg))
        p.drawText(rect, flags, text)
    else:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(int(x + dx), int(y + dy), text)
        p.setPen(QPen(fg))
        p.drawText(int(x), int(y), text)


def _draw_rotation_arrow(
    p: QPainter, rect: QRectF, rotation: int, color: QColor,
) -> None:
    """Draw a small directional triangle in the top-left corner of *rect*."""
    size = min(8.0, rect.width() * 0.2, rect.height() * 0.2)
    if size < 4:
        return
    cx = rect.left() + size + 2
    cy = rect.top() + size + 2

    # Triangle points for "up" (rotation 0), then rotate
    # Arrow points upward by default
    pts = [
        QPointF(0, -size),
        QPointF(-size * 0.6, size * 0.4),
        QPointF(size * 0.6, size * 0.4),
    ]
    angle_rad = math.radians(rotation)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    rotated = []
    for pt in pts:
        rx = pt.x() * cos_a - pt.y() * sin_a + cx
        ry = pt.x() * sin_a + pt.y() * cos_a + cy
        rotated.append(QPointF(rx, ry))

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    p.drawPolygon(QPolygonF(rotated))


# ---------------------------------------------------------------------------
# Map image renderer (shared by PNG and PDF exports)
# ---------------------------------------------------------------------------

def _render_map_image(
    grid_model: "GridModel",
    placed_with_ids: List[Tuple["PlacedTile", int]],
    title: str,
) -> QImage:
    """Render the assembly map and return it as a QImage."""
    cpx = _cell_px(grid_model.GRID_COLS, grid_model.GRID_ROWS)
    cols, rows = grid_model.GRID_COLS, grid_model.GRID_ROWS
    grid_w = cols * cpx
    grid_h = rows * cpx
    img_w = _MARGIN_PX + grid_w + _LEGEND_W_PX
    img_h = _TITLE_H_PX + _MARGIN_PX + grid_h + 10  # 10 px bottom pad

    img = QImage(img_w, img_h, QImage.Format_ARGB32)
    img.fill(QColor(Qt.white))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    grid_left = _MARGIN_PX
    grid_top = _TITLE_H_PX + _MARGIN_PX

    # ---- Title ----
    title_font = QFont("Segoe UI", 14, QFont.Bold)
    p.setFont(title_font)
    p.setPen(QPen(QColor(Qt.black)))
    title_rect = QRectF(grid_left, 4, grid_w, _TITLE_H_PX)
    p.drawText(title_rect, Qt.AlignCenter | Qt.AlignVCenter, title or "Assembly Map")

    # ---- Grid lines ----
    p.setPen(QPen(QColor(210, 210, 210), 1))
    for c in range(cols + 1):
        x = grid_left + c * cpx
        p.drawLine(x, grid_top, x, grid_top + grid_h)
    for r in range(rows + 1):
        y = grid_top + r * cpx
        p.drawLine(grid_left, y, grid_left + grid_w, y)

    # ---- Axis labels ----
    axis_font = QFont("Segoe UI", max(6, cpx // 5))
    p.setFont(axis_font)
    p.setPen(QPen(QColor(100, 100, 100)))
    x_step = _axis_step(cols)
    y_step = _axis_step(rows)
    fm = QFontMetrics(axis_font)
    for c in range(0, cols, x_step):
        x = grid_left + c * cpx + cpx // 2
        p.drawText(QRectF(x - 20, grid_top - fm.height() - 2, 40, fm.height()),
                    Qt.AlignCenter, str(c))
    for r in range(0, rows, y_step):
        y = grid_top + r * cpx + cpx // 2
        p.drawText(QRectF(grid_left - 46, y - fm.height() // 2, 42, fm.height()),
                    Qt.AlignRight | Qt.AlignVCenter, str(r))

    # ---- Tile rectangles (sorted by z_offset so top tiles paint last) ----
    tile_font = QFont("Segoe UI", max(6, cpx // 5), QFont.Bold)
    name_font = QFont("Segoe UI", max(5, cpx // 6))

    for pt, tid in sorted(placed_with_ids, key=lambda t: t[0].z_offset):
        rx = grid_left + pt.grid_x * cpx
        ry = grid_top + pt.grid_y * cpx
        rw = pt.effective_w * cpx
        rh = pt.effective_h * cpx
        tile_rect = QRectF(rx, ry, rw, rh)

        # Fill
        fill_color = QColor(pt.definition.color)
        fill_color.setAlpha(180)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill_color))
        p.drawRect(tile_rect)

        # Border
        border_color = _darker_border(pt.definition.color)
        p.setPen(QPen(border_color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(tile_rect)

        # ID label (always shown)
        fg = _contrast_color(pt.definition.color)
        outline = QColor(Qt.black) if fg == QColor(Qt.white) else QColor(Qt.white)
        p.setFont(tile_font)
        id_text = f"#{tid}"
        if pt.effective_w >= 2 and pt.effective_h >= 2:
            # ID in upper half, name in lower half
            upper = QRectF(rx, ry, rw, rh * 0.55)
            lower = QRectF(rx + 2, ry + rh * 0.45, rw - 4, rh * 0.5)
            _draw_outlined_text(p, 0, 0, id_text, fg, outline,
                                Qt.AlignCenter, upper)
            p.setFont(name_font)
            # Elide name if needed
            elided = QFontMetrics(name_font).elidedText(
                pt.definition.name, Qt.ElideRight, int(rw - 4))
            _draw_outlined_text(p, 0, 0, elided, fg, outline,
                                Qt.AlignCenter, lower)
        else:
            _draw_outlined_text(p, 0, 0, id_text, fg, outline,
                                Qt.AlignCenter, tile_rect)

        # Rotation arrow
        arrow_color = QColor(fg)
        arrow_color.setAlpha(180)
        _draw_rotation_arrow(p, tile_rect, pt.rotation, arrow_color)

        # Z-offset badge
        if pt.z_offset > 0:
            badge_font = QFont("Segoe UI", max(5, cpx // 7))
            p.setFont(badge_font)
            bfm = QFontMetrics(badge_font)
            badge_text = f"Z={pt.z_offset:.0f}"
            bw = bfm.horizontalAdvance(badge_text) + 6
            bh = bfm.height() + 2
            bx = rx + rw - bw - 2
            by = ry + 2
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 220, 50, 220)))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
            p.setPen(QPen(QColor(Qt.black)))
            p.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, badge_text)

    # ---- Legend (right side) ----
    lx = grid_left + grid_w + 16
    ly = grid_top
    legend_font = QFont("Segoe UI", 9)
    legend_header_font = QFont("Segoe UI", 11, QFont.Bold)
    swatch_size = 14
    line_h = 20

    # Header
    p.setFont(legend_header_font)
    p.setPen(QPen(QColor(Qt.black)))
    p.drawText(lx, ly + 14, "Legend")
    ly += 28

    # Unique tile types
    seen_names: dict = {}
    for pt, _ in placed_with_ids:
        if pt.definition.name not in seen_names:
            seen_names[pt.definition.name] = pt.definition

    p.setFont(legend_font)
    for name in sorted(seen_names):
        defn = seen_names[name]
        if ly + line_h > img_h - 10:
            p.drawText(lx, ly + 12, "... (see CSV)")
            break
        # Swatch
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(defn.color))
        p.drawRect(lx, ly, swatch_size, swatch_size)
        p.setPen(QPen(QColor(60, 60, 60)))
        p.drawRect(lx, ly, swatch_size, swatch_size)
        # Name + dims
        text = f"{name}  ({defn.grid_w}\u00d7{defn.grid_h})"
        p.drawText(lx + swatch_size + 6, ly + 12, text)
        ly += line_h

    ly += 10
    # Separator
    p.setPen(QPen(QColor(180, 180, 180)))
    p.drawLine(lx, ly, lx + _LEGEND_W_PX - 32, ly)
    ly += 10

    # Placement list
    p.setFont(legend_header_font)
    p.setPen(QPen(QColor(Qt.black)))
    p.drawText(lx, ly + 14, "Placements")
    ly += 24

    small_font = QFont("Segoe UI", 8)
    p.setFont(small_font)
    shown = 0
    for pt, tid in placed_with_ids:
        if ly + line_h > img_h - 10 or shown >= _MAX_LEGEND_ENTRIES:
            remaining = len(placed_with_ids) - shown
            if remaining > 0:
                p.drawText(lx, ly + 10, f"... and {remaining} more (see CSV)")
            break
        rx_val = f"{pt.grid_x:.0f}" if pt.grid_x == int(pt.grid_x) else f"{pt.grid_x:.1f}"
        ry_val = f"{pt.grid_y:.0f}" if pt.grid_y == int(pt.grid_y) else f"{pt.grid_y:.1f}"
        entry = f"#{tid}: {pt.definition.name} @ ({rx_val},{ry_val}) R={pt.rotation}\u00b0"
        p.setPen(QPen(QColor(40, 40, 40)))
        p.drawText(lx + 2, ly + 10, entry)
        ly += line_h - 4
        shown += 1

    p.end()
    return img


def _render_map_png(
    grid_model: "GridModel",
    placed_with_ids: List[Tuple["PlacedTile", int]],
    png_path: str,
    title: str,
) -> None:
    img = _render_map_image(grid_model, placed_with_ids, title)
    img.save(png_path, "PNG")


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def _write_assembly_csv(
    placed_with_ids: List[Tuple["PlacedTile", int]],
    csv_path: str,
) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "name", "stl_path",
            "grid_x", "grid_y", "rotation",
            "z_offset", "effective_w", "effective_h",
        ])
        for pt, tid in placed_with_ids:
            writer.writerow([
                tid,
                pt.definition.name,
                pt.definition.stl_path,
                pt.grid_x,
                pt.grid_y,
                pt.rotation,
                pt.z_offset,
                pt.effective_w,
                pt.effective_h,
            ])


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------

def _render_pdf(
    grid_model: "GridModel",
    placed_with_ids: List[Tuple["PlacedTile", int]],
    pdf_path: str,
    title: str,
) -> None:
    """Render a combined PDF: page 1 = assembly map, page 2+ = placement table."""
    from PyQt5.QtGui import QPdfWriter

    map_img = _render_map_image(grid_model, placed_with_ids, title)

    # --- Set up PDF writer (landscape A4) ---
    writer = QPdfWriter(pdf_path)
    landscape = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Landscape,
        QMarginsF(15, 15, 15, 15),  # mm
    )
    writer.setPageLayout(landscape)
    writer.setResolution(150)
    dpi = writer.resolution()

    p = QPainter(writer)

    page_w = writer.width()   # device pixels
    page_h = writer.height()

    # ---- Page 1: Assembly map image, scaled to fit ----
    img_w, img_h = map_img.width(), map_img.height()
    scale = min(page_w / img_w, page_h / img_h)
    draw_w = int(img_w * scale)
    draw_h = int(img_h * scale)
    x_off = (page_w - draw_w) // 2
    y_off = (page_h - draw_h) // 2
    p.drawImage(QRect(x_off, y_off, draw_w, draw_h), map_img)

    # ---- Page 2+: Placement table ----
    writer.newPage()

    mm = dpi / 25.4  # pixels per mm

    # Fonts
    title_font = QFont("Segoe UI", 14, QFont.Bold)
    header_font = QFont("Segoe UI", 9, QFont.Bold)
    body_font = QFont("Segoe UI", 8)
    body_fm = QFontMetrics(body_font)
    header_fm = QFontMetrics(header_font)

    row_h = int(body_fm.height() * 1.6)
    header_h = int(header_fm.height() * 1.8)

    # Column layout (proportional widths)
    col_defs = [
        ("ID",    0.05),
        ("Name",  0.25),
        ("STL Path", 0.30),
        ("X",     0.06),
        ("Y",     0.06),
        ("Rot",   0.06),
        ("Z",     0.06),
        ("W",     0.06),
        ("H",     0.06),
    ]
    table_left = int(5 * mm)
    table_w = page_w - int(10 * mm)
    col_widths = [int(table_w * frac) for _, frac in col_defs]
    # Distribute rounding remainder to the widest column
    remainder = table_w - sum(col_widths)
    col_widths[2] += remainder  # STL Path gets the slack

    def _draw_table_header(y: int) -> int:
        """Draw column headers and return the y below the header."""
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(55, 55, 55)))
        p.drawRect(table_left, y, table_w, header_h)
        p.setFont(header_font)
        p.setPen(QPen(QColor(Qt.white)))
        cx = table_left
        for i, (label, _) in enumerate(col_defs):
            p.drawText(QRectF(cx + 4, y, col_widths[i] - 8, header_h),
                        Qt.AlignVCenter | Qt.AlignLeft, label)
            cx += col_widths[i]
        return y + header_h

    def _draw_row(y: int, row_data: list, bg: QColor) -> int:
        """Draw one data row and return the y below it."""
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRect(table_left, y, table_w, row_h)
        p.setFont(body_font)
        p.setPen(QPen(QColor(30, 30, 30)))
        cx = table_left
        for i, val in enumerate(row_data):
            text = str(val)
            elided = body_fm.elidedText(text, Qt.ElideRight, col_widths[i] - 8)
            p.drawText(QRectF(cx + 4, y, col_widths[i] - 8, row_h),
                        Qt.AlignVCenter | Qt.AlignLeft, elided)
            cx += col_widths[i]
        return y + row_h

    # Title
    p.setFont(title_font)
    p.setPen(QPen(QColor(Qt.black)))
    title_h = int(12 * mm)
    p.drawText(QRectF(table_left, 0, table_w, title_h),
               Qt.AlignVCenter | Qt.AlignLeft,
               (title or "Assembly Map") + " \u2014 Placement List")
    cur_y = title_h + int(2 * mm)

    # Summary line
    total = len(placed_with_ids)
    unique = len({pt.definition.name for pt, _ in placed_with_ids})
    summary_font = QFont("Segoe UI", 9)
    p.setFont(summary_font)
    p.setPen(QPen(QColor(80, 80, 80)))
    p.drawText(QRectF(table_left, cur_y, table_w, int(5 * mm)),
               Qt.AlignVCenter | Qt.AlignLeft,
               f"{total} placements  \u00b7  {unique} unique tile types  "
               f"\u00b7  Grid {grid_model.GRID_COLS}\u00d7{grid_model.GRID_ROWS}")
    cur_y += int(7 * mm)

    # Table header
    cur_y = _draw_table_header(cur_y)

    # Table rows
    even_bg = QColor(255, 255, 255)
    odd_bg = QColor(240, 240, 245)
    for idx, (pt, tid) in enumerate(placed_with_ids):
        # Check if we need a new page
        if cur_y + row_h > page_h - int(5 * mm):
            writer.newPage()
            cur_y = int(5 * mm)
            cur_y = _draw_table_header(cur_y)

        gx = f"{pt.grid_x:.0f}" if pt.grid_x == int(pt.grid_x) else f"{pt.grid_x:.1f}"
        gy = f"{pt.grid_y:.0f}" if pt.grid_y == int(pt.grid_y) else f"{pt.grid_y:.1f}"
        zo = f"{pt.z_offset:.0f}" if pt.z_offset == int(pt.z_offset) else f"{pt.z_offset:.1f}"
        row = [
            tid,
            pt.definition.name,
            pt.definition.stl_path,
            gx, gy,
            f"{pt.rotation}\u00b0",
            zo,
            pt.effective_w,
            pt.effective_h,
        ]
        bg = even_bg if idx % 2 == 0 else odd_bg
        cur_y = _draw_row(cur_y, row, bg)

    p.end()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_assembly_map(
    grid_model: "GridModel",
    base_path: str,
    title: str = "",
) -> Tuple[str, str]:
    """Export an assembly map PNG and detailed placement CSV.

    *base_path* is used without extension; the function appends
    ``_assembly_map.png`` and ``_assembly_list.csv``.

    Returns ``(png_path, csv_path)``.
    """
    placed = grid_model.all_placed()

    # Assign IDs sorted by layer, then top-to-bottom, left-to-right
    ordered = sorted(placed, key=lambda t: (t.z_offset, t.grid_y, t.grid_x))
    placed_with_ids: List[Tuple["PlacedTile", int]] = [
        (tile, idx + 1) for idx, tile in enumerate(ordered)
    ]

    png_path = base_path + "_assembly_map.png"
    csv_path = base_path + "_assembly_list.csv"

    _render_map_png(grid_model, placed_with_ids, png_path, title)
    _write_assembly_csv(placed_with_ids, csv_path)

    return png_path, csv_path


def export_assembly_pdf(
    grid_model: "GridModel",
    pdf_path: str,
    title: str = "",
) -> str:
    """Export a combined PDF with the assembly map and placement table.

    Returns the PDF path.
    """
    placed = grid_model.all_placed()
    ordered = sorted(placed, key=lambda t: (t.z_offset, t.grid_y, t.grid_x))
    placed_with_ids: List[Tuple["PlacedTile", int]] = [
        (tile, idx + 1) for idx, tile in enumerate(ordered)
    ]

    _render_pdf(grid_model, placed_with_ids, pdf_path, title)
    return pdf_path
