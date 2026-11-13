"""The dashboard centrepiece: a 3D stack of frosted-glass folders, one per tool.

The folders stand in a row and are projected through a simple perspective
camera, so the ones in the middle are seen edge-on and the outer ones open up
towards the viewer. Each folder is painted flat (tab, papers, front flap,
label) and then mapped onto its projected quadrilateral, which keeps rounded
corners and text correctly foreshortened. A blurred copy of the scene is
added underneath for the soft glow of glass.

Hovering a folder lifts it out of the stack in green and shows a glass info
card; clicking (or Enter) opens the tool; ← / → or the round handle above the
stack move the selection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QTransform,
)
from PySide6.QtWidgets import QWidget

from officeflow.gui import icons, theme


@dataclass
class FanItem:
    id: str
    title: str
    caption: str   # small line under the title, e.g. "PDF · 12 runs"
    stat: str      # big figure, e.g. "87%" or "New"
    icon: str = "pdf"


# Folder drawn in its own flat coordinate system, then projected.
LW, LH = 320.0, 250.0
_LOCAL = QPolygonF([QPointF(0, 0), QPointF(LW, 0), QPointF(LW, LH), QPointF(0, LH)])

# World: folders stand on y = 0, extend along +z (away from the camera).
DEPTH, HEIGHT = 1.0, 0.80
SPACING = 0.24
CAMERA_Y = 1.15
DISTANCE = 3.1
YAW = 0.30          # the left end of the row is closer to the viewer than the right end
FAN = 0.08          # outer folders turn towards the viewer
OPEN = 0.40         # extra turn of the selected folder


@dataclass
class _Card:
    index: int
    quad: QPolygonF          # screen corners: top-left, top-right, bottom-right, bottom-left
    near_left: bool          # the front (near) edge is on the left of the screen
    depth: float


class FolderFan(QWidget):
    selectedChanged = Signal(str)
    activated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._items: list[FanItem] = []
        self._selected = 0
        self._lift: list[float] = []          # animated 0 → 1 for the selected folder
        self._cards: list[_Card] = []
        self._cache: QImage | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._animate)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(380)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # -- public API ------------------------------------------------------
    def set_items(self, items: list[FanItem], selected_id: str = "") -> None:
        self._items = items
        ids = [i.id for i in items]
        self._selected = ids.index(selected_id) if selected_id in ids else 0
        self._lift = [1.0 if i == self._selected else 0.0 for i in range(len(items))]
        self._invalidate()

    def selected_id(self) -> str:
        return self._items[self._selected].id if self._items else ""

    def select(self, index: int) -> None:
        if not self._items:
            return
        index = max(0, min(index, len(self._items) - 1))
        if index != self._selected:
            self._selected = index
            self.selectedChanged.emit(self._items[index].id)
            self._timer.start()

    # -- geometry --------------------------------------------------------
    def _layout(self) -> None:
        """Project every folder and fit the whole stack into the widget."""
        count = len(self._items)
        centre = (count - 1) / 2
        raw: list[tuple[int, list[tuple[float, float]], float, float]] = []
        for i in range(count):
            u = (i - centre) / (centre or 1)                       # -1 … +1
            # neighbours of the selected folder step aside to make room
            push = sum((0.16 if i > j else -0.16 if i < j else 0.0) * self._lift[j]
                       for j in range(count) if j != i)
            x = (i - centre) * SPACING + push
            lift = self._lift[i]
            z = DISTANCE + x * math.tan(YAW) - 0.22 * lift
            # outer folders open towards the viewer; the selected one opens fully
            side = -1.0 if u <= 0 else 1.0
            # near the centre perspective shows folders edge-on, so open those further
            opening = OPEN + 0.55 * (1 - min(abs(u) * 2.5, 1.0))
            angle = -FAN * math.copysign(abs(u) ** 0.8, u) - side * opening * lift
            dx, dz = math.sin(angle) * DEPTH, math.cos(angle) * DEPTH
            y0, y1 = 0.10 * lift, HEIGHT * (1 + 0.10 * lift) + 0.10 * lift
            near_b, near_t = (x, y0, z), (x, y1, z)
            far_b, far_t = (x + dx, y0, z + dz), (x + dx, y1, z + dz)
            points = [self._project(p) for p in (near_t, far_t, far_b, near_b)]
            raw.append((i, points, z + dz / 2, x))
        xs = [p[0] for _, pts, _, _ in raw for p in pts]
        ys = [p[1] for _, pts, _, _ in raw for p in pts]
        margin_x, top, bottom = 30.0, 78.0, 18.0
        scale = min((self.width() - 2 * margin_x) / (max(xs) - min(xs)),
                    (self.height() - top - bottom) / (max(ys) - min(ys)))
        offset_x = (self.width() - (max(xs) - min(xs)) * scale) / 2 - min(xs) * scale
        offset_y = top + (self.height() - top - bottom - (max(ys) - min(ys)) * scale) / 2 - min(ys) * scale
        self._cards = []
        for i, pts, depth, x in raw:
            near_t, far_t, far_b, near_b = (QPointF(px * scale + offset_x, py * scale + offset_y) for px, py in pts)
            near_left = near_t.x() <= far_t.x()
            quad = (QPolygonF([near_t, far_t, far_b, near_b]) if near_left
                    else QPolygonF([far_t, near_t, near_b, far_b]))
            self._cards.append(_Card(i, quad, near_left, abs(x)))

    @staticmethod
    def _project(point: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = point
        return x / z, (CAMERA_Y - y) / z

    def _paint_order(self) -> list[_Card]:
        """Outer folders first so the ones closer to the centre overlap them;
        the selected folder is always drawn last, on top."""
        order = sorted(self._cards, key=lambda c: -c.depth)
        order.sort(key=lambda c: c.index == self._selected)
        return order

    def _index_at(self, position: QPointF) -> int:
        if self._cache is None or not self._cards:
            self._layout()   # geometry may be stale until the next paint
        for card in reversed(self._paint_order()):
            if card.quad.containsPoint(position, Qt.FillRule.OddEvenFill):
                return card.index
        return -1

    # -- interaction -----------------------------------------------------
    def _handle_rect(self) -> QRectF:
        return QRectF(self.width() / 2 - 17, 19, 34, 34)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if index >= 0:
            self.select(index)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._handle_rect().adjusted(-6, -6, 6, 6).contains(event.position()):
            step = -1 if event.position().x() < self._handle_rect().center().x() else 1
            self.select(self._selected + step)
            return
        index = self._index_at(event.position())
        if index >= 0:
            self.activated.emit(self._items[index].id)

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self.select(self._selected + (1 if delta < 0 else -1))
            event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.select(self._selected - 1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.select(self._selected + 1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._items:
            self.activated.emit(self.selected_id())
        else:
            super().keyPressEvent(event)

    def _animate(self) -> None:
        done = True
        for i, value in enumerate(self._lift):
            target = 1.0 if i == self._selected else 0.0
            value += (target - value) * 0.28
            if abs(target - value) < 0.01:
                value = target
            else:
                done = False
            self._lift[i] = value
        if done:
            self._timer.stop()
        self._invalidate()

    def _invalidate(self) -> None:
        self._cache = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._cache = None
        super().resizeEvent(event)

    # -- painting --------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._items:
            return
        if self._cache is None:
            self._layout()
            self._cache = self._render_scene()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_handle(painter)
        painter.drawImage(QRectF(0, 0, self.width(), self.height()), self._cache)
        self._paint_info(painter)
        painter.end()

    def _render_scene(self) -> QImage:
        ratio = self.devicePixelRatioF()
        size = QSize(max(1, int(self.width() * ratio)), max(1, int(self.height() * ratio)))
        sharp = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        sharp.setDevicePixelRatio(ratio)
        sharp.fill(Qt.GlobalColor.transparent)
        painter = QPainter(sharp)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                               | QPainter.RenderHint.SmoothPixmapTransform)
        dark = theme.current().name == "dark"
        for card in self._paint_order():
            self._paint_folder(painter, card, dark)
        painter.end()

        # Glow: a heavily blurred copy (down- then up-scaled) under the sharp image.
        result = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
        result.setDevicePixelRatio(ratio)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        smooth = Qt.TransformationMode.SmoothTransformation
        glow = sharp.scaled(max(1, size.width() // 10), max(1, size.height() // 10),
                            Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
        glow = glow.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
        glow.setDevicePixelRatio(ratio)
        painter.setOpacity(0.75 if dark else 0.35)
        painter.drawImage(0, 0, glow)
        painter.setOpacity(1.0)
        painter.drawImage(0, 0, sharp)
        painter.end()
        return result

    def _paint_folder(self, painter: QPainter, card: _Card, dark: bool) -> None:
        transform = QTransform()
        if not QTransform.quadToQuad(_LOCAL, card.quad, transform):
            return
        item = self._items[card.index]
        lift = self._lift[card.index]
        selected = card.index == self._selected
        # fade folders that are far from the centre or far away from the viewer
        fade = 1.0 - 0.45 * min(card.depth / (SPACING * len(self._items) / 2 + 0.3), 1.0)
        painter.save()
        painter.setTransform(transform)

        green = QColor(104, 231, 142)
        stroke_light = QColor(255, 255, 255, int(170 * fade)) if dark else QColor(0, 11, 26, int(55 * fade))

        # back panel with the folder tab
        back = QPainterPath()
        tab_x0, tab_x1 = (14, 128) if card.near_left else (LW - 128, LW - 14)
        r = 18
        back.moveTo(0, 34 + r)
        back.quadTo(0, 34, r, 34)
        if card.near_left:
            back.lineTo(tab_x0, 34)
            back.cubicTo(tab_x0 + 8, 34, tab_x0 + 6, 6, tab_x0 + 24, 6)
            back.lineTo(tab_x1 - 24, 6)
            back.cubicTo(tab_x1 - 6, 6, tab_x1 - 8, 34, tab_x1, 34)
        else:
            back.lineTo(tab_x0, 34)
            back.cubicTo(tab_x0 + 8, 34, tab_x0 + 6, 6, tab_x0 + 24, 6)
            back.lineTo(tab_x1 - 24, 6)
            back.cubicTo(tab_x1 - 6, 6, tab_x1 - 8, 34, tab_x1, 34)
        back.lineTo(LW - r, 34)
        back.quadTo(LW, 34, LW, 34 + r)
        back.lineTo(LW, LH - r)
        back.quadTo(LW, LH, LW - r, LH)
        back.lineTo(r, LH)
        back.quadTo(0, LH, 0, LH - r)
        back.closeSubpath()
        fill = QLinearGradient(0, 0, 0, LH)
        if selected or lift > 0.5:
            fill.setColorAt(0, QColor(46, 160, 88, 245))
            fill.setColorAt(1, QColor(20, 112, 56, 240))
        elif dark:
            fill.setColorAt(0, QColor(255, 255, 255, int(165 * fade)))
            fill.setColorAt(0.45, QColor(255, 255, 255, int(55 * fade)))
            fill.setColorAt(1, QColor(255, 255, 255, int(6 * fade)))
        else:
            fill.setColorAt(0, QColor(255, 255, 255, int(235 * fade)))
            fill.setColorAt(1, QColor(255, 255, 255, int(150 * fade)))
        pen = QPen(QColor(190, 255, 210, 230) if selected else stroke_light, 1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawPath(back)

        # papers peeking out of the folder, with document lines
        painter.setPen(Qt.PenStyle.NoPen)
        for k in range(2):
            px = 34 + k * 26 if card.near_left else LW - 34 - k * 26 - 210
            paper = QRectF(px, 46 - k * 8 + (0 if k else 6), 210, 120)
            paper_fill = QColor(255, 255, 255, int((235 if selected else 150 if dark else 255) * fade))
            painter.setBrush(paper_fill)
            painter.drawRoundedRect(paper, 10, 10)
            painter.setBrush(QColor(0, 11, 26, int((38 if not selected else 46) * fade)))
            for row in range(4):
                width = (150, 110, 135, 90)[row]
                painter.drawRoundedRect(QRectF(paper.left() + 18, paper.top() + 18 + row * 16, width, 7), 3.5, 3.5)

        # front flap
        front = QPainterPath()
        top = 112
        dip = 26
        front.moveTo(0, top + r)
        front.quadTo(0, top, r, top)
        if card.near_left:
            front.lineTo(LW * 0.42, top)
            front.cubicTo(LW * 0.55, top, LW * 0.52, top + dip, LW * 0.66, top + dip)
            front.lineTo(LW - r, top + dip)
            front.quadTo(LW, top + dip, LW, top + dip + r)
        else:
            front.lineTo(LW * 0.34, top + dip)
            front.cubicTo(LW * 0.48, top + dip, LW * 0.45, top, LW * 0.58, top)
            front.lineTo(LW - r, top)
            front.quadTo(LW, top, LW, top + r)
        front.lineTo(LW, LH - r)
        front.quadTo(LW, LH, LW - r, LH)
        front.lineTo(r, LH)
        front.quadTo(0, LH, 0, LH - r)
        front.closeSubpath()
        flap = QLinearGradient(0, top, LW, LH)
        if selected or lift > 0.5:
            flap.setColorAt(0, QColor(green.red(), green.green(), green.blue(), 245))
            flap.setColorAt(1, QColor(52, 172, 98, 240))
        elif dark:
            flap = QLinearGradient(0, top, 0, LH)
            flap.setColorAt(0, QColor(245, 247, 246, int(200 * fade)))
            flap.setColorAt(0.5, QColor(225, 230, 228, int(95 * fade)))
            flap.setColorAt(1, QColor(200, 205, 203, int(18 * fade)))
        else:
            flap.setColorAt(0, QColor(250, 251, 252, int(250 * fade)))
            flap.setColorAt(1, QColor(222, 227, 232, int(235 * fade)))
        painter.setPen(pen)
        painter.setBrush(flap)
        painter.drawPath(front)

        # icon and label on the flap, close to the front edge
        ink = QColor(255, 255, 255) if selected else QColor(30, 34, 38, int(215 * fade)) if not dark \
            else QColor(215, 220, 224, int(225 * fade))
        icon_x = 26 if card.near_left else LW - 26 - 34
        glyph = icons.pixmap(item.icon, "#FFFFFF" if selected or dark else theme.INK, 34)
        painter.setOpacity(1.0 if selected else 0.75 * fade)
        painter.drawPixmap(QRectF(icon_x, top + 40, 30, 30), glyph, QRectF(glyph.rect()))
        painter.setOpacity(1.0)
        font = QFont(self.font())
        font.setPixelSize(23)
        font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(ink)
        text_rect = QRectF(24, LH - 58, LW - 48, 36)
        text = painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        align = Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if card.near_left
                                                 else Qt.AlignmentFlag.AlignRight)
        painter.drawText(text_rect, int(align), text)
        painter.restore()

    def _paint_handle(self, painter: QPainter) -> None:
        accent = QColor(theme.ACCENT)
        rect = self._handle_rect()
        width = self.width()
        path = QPainterPath(QPointF(width * 0.30, 112))
        path.cubicTo(QPointF(width * 0.40, 30), QPointF(width * 0.60, 30), QPointF(width * 0.70, 112))
        gradient = QLinearGradient(width * 0.30, 0, width * 0.70, 0)
        for stop, alpha in ((0, 0), (0.5, 210), (1, 0)):
            colour = QColor(accent)
            colour.setAlpha(alpha)
            gradient.setColorAt(stop, colour)
        painter.setPen(QPen(gradient, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        glow = QColor(accent)
        glow.setAlpha(40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(rect.adjusted(-5, -5, 5, 5))
        painter.setPen(QPen(accent, 1.3))
        painter.setBrush(QColor(theme.current().window))
        painter.drawEllipse(rect)
        c = rect.center()
        painter.drawPolyline([c + QPointF(-3, -4), c + QPointF(-7, 0), c + QPointF(-3, 4)])
        painter.drawPolyline([c + QPointF(3, -4), c + QPointF(7, 0), c + QPointF(3, 4)])

    def _paint_info(self, painter: QPainter) -> None:
        card = next((c for c in self._cards if c.index == self._selected), None)
        if card is None:
            return
        item = self._items[self._selected]
        box = card.quad.boundingRect()
        width, height = 200.0, 118.0
        left_room = box.left() - 12
        x = box.left() - width + 34 if left_room > width - 34 else box.right() - 34
        x = max(12.0, min(x, self.width() - width - 12))
        rect = QRectF(x, box.top() + box.height() * 0.22, width, height)
        shadow = QColor(0, 0, 0, 70 if theme.current().name == "dark" else 25)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(rect.translated(0, 8), 20, 20)
        glass = QLinearGradient(rect.topLeft(), rect.bottomRight())
        glass.setColorAt(0, QColor(252, 253, 253, 246))
        glass.setColorAt(0.6, QColor(236, 244, 239, 236))
        glass.setColorAt(1, QColor(200, 238, 212, 228))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
        painter.setBrush(glass)
        painter.drawRoundedRect(rect, 20, 20)
        ink = QColor(theme.INK)
        font = QFont(self.font())
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(ink)
        title = painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, int(width - 52))
        painter.drawText(QPointF(rect.left() + 16, rect.top() + 28), title)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(0, 11, 26, 120))
        painter.drawText(QPointF(rect.left() + 16, rect.top() + 46), item.caption)
        font.setPixelSize(32)
        font.setWeight(QFont.Weight.Light)
        painter.setFont(font)
        painter.setPen(QColor(0, 11, 26, 190))
        painter.drawText(QPointF(rect.left() + 16, rect.bottom() - 16), item.stat)
        painter.setPen(QPen(ink, 1.4))
        tip = QPointF(rect.right() - 18, rect.top() + 18)
        painter.drawLine(tip + QPointF(-8, 8), tip)
        painter.drawPolyline([tip + QPointF(-6, 0), tip, tip + QPointF(0, 6)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 129, 60))
        painter.drawEllipse(QPointF(rect.right() - 22, rect.bottom() - 24), 4.5, 4.5)
