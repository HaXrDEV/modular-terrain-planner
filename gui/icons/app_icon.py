from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient


def create_app_icon() -> QIcon:
    """Draw the application icon programmatically and return a QIcon."""
    size = 256
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Clip everything to the rounded-rect shape
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), 44, 44)
    p.setClipPath(clip)

    # Dark background
    bg = QRadialGradient(QPointF(0.35 * size, 0.35 * size), 0.65 * size)
    bg.setColorAt(0, QColor("#1c1c38"))
    bg.setColorAt(1, QColor("#080810"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRect(0, 0, size, size)

    # Warm torch-light glow (upper-left)
    glow = QRadialGradient(QPointF(0.22 * size, 0.22 * size), 0.40 * size)
    glow.setColorAt(0, QColor(200, 112, 32, 51))
    glow.setColorAt(1, QColor(200, 112, 32, 0))
    p.setBrush(glow)
    p.drawRect(0, 0, size, size)

    # ── Isometric 2×2 dungeon floor tiles ──────────────────────────────────
    # Diamond half-widths: w=50 (x), h=25 (y).  Side depth: d=18 px.
    # Tile centres (screen):
    #   (0,0)→(128,100)  (1,0)→(178,125)
    #   (0,1)→( 78,125)  (1,1)→(128,150)
    w, h, d = 50, 25, 18
    tiles = [
        (128, 100, "#6a6a84"),
        (178, 125, "#64647e"),
        ( 78, 125, "#66667e"),
        (128, 150, "#606078"),
    ]

    def poly(*pts: tuple) -> QPolygonF:
        return QPolygonF([QPointF(x, y) for x, y in pts])

    for cx, cy, top_color in tiles:
        N  = (cx,     cy - h)
        E  = (cx + w, cy)
        S  = (cx,     cy + h)
        W  = (cx - w, cy)
        Sd = (cx,     cy + h + d)
        Wd = (cx - w, cy + d)
        Ed = (cx + w, cy + d)

        # Left side face
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#232335"))
        p.drawPolygon(poly(W, S, Sd, Wd))

        # Right side face
        p.setBrush(QColor("#2e2e48"))
        p.drawPolygon(poly(S, E, Ed, Sd))

        # Top face
        p.setBrush(QColor(top_color))
        p.setPen(QPen(QColor("#9898b8"), 1.2))
        p.drawPolygon(poly(N, E, S, W))

        # Mortar lines — divide each tile into a 2×2 stone-block grid
        mNW = ((N[0] + W[0]) / 2, (N[1] + W[1]) / 2)
        mSE = ((S[0] + E[0]) / 2, (S[1] + E[1]) / 2)
        mNE = ((N[0] + E[0]) / 2, (N[1] + E[1]) / 2)
        mSW = ((S[0] + W[0]) / 2, (S[1] + W[1]) / 2)
        p.setPen(QPen(QColor("#3e3e58"), 1.0))
        p.drawLine(QPointF(*mNW), QPointF(*mSE))
        p.drawLine(QPointF(*mNE), QPointF(*mSW))

        # Lit top-edge highlights
        p.setPen(QPen(QColor(192, 192, 220, 153), 1.6))
        p.drawLine(QPointF(*N), QPointF(*E))
        p.setPen(QPen(QColor(192, 192, 220, 107), 1.6))
        p.drawLine(QPointF(*N), QPointF(*W))

    p.end()
    return QIcon(px)
