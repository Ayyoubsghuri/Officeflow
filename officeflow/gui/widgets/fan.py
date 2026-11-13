"""The dashboard centrepiece: a fan of translucent folder cards, one per tool.

Hovering a card highlights it in green and shows a glass info card; clicking
opens the tool. Everything is painted by hand so it scales with the window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from officeflow.gui import theme


@dataclass
class FanItem:
    id: str
    title: str
    caption: str   # small line under the title, e.g. "PDF · 12 runs"
    stat: str      # big figure, e.g. "87%" or "New"


class FolderFan(QWidget):
    selectedChanged = Signal(str)
    activated = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._items: list[FanItem] = []
        self._selected = 0
        self.setMouseTracking(True)
        self.setMinimumHeight(340)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_items(self, items: list[FanItem], selected_id: str = "") -> None:
        self._items = items
        ids = [i.id for i in items]
        self._selected = ids.index(selected_id) if selected_id in ids else 0
        self.update()

    def selected_id(self) -> str:
        return self._items[self._selected].id if self._items else ""

    # -- geometry --------------------------------------------------------
    def _card(self, index: int) -> tuple[QPolygonF, float, float]:
        """Polygon of card ``index`` plus its side (-1 left, +1 right) and face width."""
        count = len(self._items)
        centre = (count - 1) / 2 or 1
        u = (index - centre) / centre                     # -1 … +1 across the fan
        side = -1.0 if u < 0 else 1.0
        width, height = self.width(), self.height()
        base = height - 46
        tall = min(height - 130, 250)
        selected = index == self._selected
        x = width / 2 + u * (width / 2 - 150)
        face = 12 + 74 * abs(u) ** 1.15 + (46 if selected else 0)
        lean = u * 56
        lift = 14 if selected else 0
        points = [
            QPointF(x, base - lift),
            QPointF(x + lean, base - tall - lift),
            QPointF(x + side * face + lean * 1.12, base - tall * 0.93 - 6 - lift),
            QPointF(x + side * face, base - 12 - lift),
        ]
        return QPolygonF(points), side, face

    def _index_at(self, position: QPointF) -> int:
        best, distance = -1, 1e9
        for index in range(len(self._items)):
            polygon, _, _ = self._card(index)
            box = polygon.boundingRect()
            if polygon.containsPoint(position, Qt.FillRule.OddEvenFill):
                return index
            gap = abs(box.center().x() - position.x())
            if box.top() - 20 <= position.y() <= box.bottom() + 20 and gap < distance:
                best, distance = index, gap
        return best if distance < 60 else -1

    # -- interaction -----------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if index >= 0 and index != self._selected:
            self._selected = index
            self.selectedChanged.emit(self._items[index].id)
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and index >= 0:
            self.activated.emit(self._items[index].id)

    # -- painting --------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._items:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = theme.current().name == "dark"
        tint = QColor(255, 255, 255) if dark else QColor(0, 11, 26)
        self._paint_arc(painter)
        centre = (len(self._items) - 1) / 2
        order = sorted(range(len(self._items)), key=lambda i: -abs(i - centre))
        for index in order:
            if index != self._selected:
                self._paint_card(painter, index, tint, dark)
        self._paint_card(painter, self._selected, tint, dark)
        self._paint_info(painter)
        painter.end()

    def _paint_arc(self, painter: QPainter) -> None:
        width = self.width()
        accent = QColor(theme.ACCENT)
        path = QPainterPath(QPointF(width / 2 - 150, 78))
        path.quadTo(QPointF(width / 2, -6), QPointF(width / 2 + 150, 78))
        gradient = QLinearGradient(width / 2 - 150, 0, width / 2 + 150, 0)
        for stop, alpha in ((0, 0), (0.5, 200), (1, 0)):
            colour = QColor(accent)
            colour.setAlpha(alpha)
            gradient.setColorAt(stop, colour)
        painter.setPen(QPen(gradient, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(QPen(accent, 1.3))
        painter.setBrush(QColor(theme.current().window))
        painter.drawEllipse(QPointF(width / 2, 36), 15, 15)
        painter.drawPolyline([QPointF(width / 2 - 3, 31), QPointF(width / 2 - 8, 36), QPointF(width / 2 - 3, 41)])
        painter.drawPolyline([QPointF(width / 2 + 3, 31), QPointF(width / 2 + 8, 36), QPointF(width / 2 + 3, 41)])

    def _paint_card(self, painter: QPainter, index: int, tint: QColor, dark: bool) -> None:
        polygon, side, face = self._card(index)
        selected = index == self._selected
        box = polygon.boundingRect()
        gradient = QLinearGradient(box.topLeft(), box.bottomRight() if side > 0 else box.bottomLeft())
        if selected:
            gradient.setColorAt(0, QColor(104, 231, 142, 250))
            gradient.setColorAt(1, QColor(23, 122, 62, 245))
            edge = QColor(170, 255, 196, 230)
        else:
            top, bottom = (QColor(tint), QColor(tint))
            top.setAlpha(150 if dark else 46)
            bottom.setAlpha(26 if dark else 14)
            gradient.setColorAt(0, top)
            gradient.setColorAt(1, bottom)
            edge = QColor(tint)
            edge.setAlpha(120 if dark else 70)
        pen = QPen(edge, 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(gradient)
        painter.drawPolygon(polygon)

        a, b, c, d = (polygon[i] for i in range(4))
        if face > 44:  # "document lines" on cards that face the viewer
            painter.setPen(Qt.PenStyle.NoPen)
            line = QColor(255, 255, 255, 150 if selected or dark else 0) if (selected or dark) else QColor(0, 11, 26, 40)
            painter.setBrush(line)
            for row in range(5):
                t = 0.12 + row * 0.055
                left = QPointF(b.x() + (a.x() - b.x()) * t + side * face * 0.22, b.y() + (a.y() - b.y()) * t)
                length = face * (0.5 if row % 2 else 0.36)
                painter.drawRoundedRect(QRectF(min(left.x(), left.x() + side * length), left.y(), length, 4), 2, 2)
        if face > 30:  # title written up the card, like a folder tab label
            item = self._items[index]
            painter.save()
            mid = QPointF((a.x() + d.x()) / 2, (a.y() + d.y()) / 2 - 16)
            painter.translate(mid)
            painter.rotate(-90 + math.degrees(math.atan2(b.x() - a.x(), a.y() - b.y())))
            font = QFont(self.font())
            font.setPointSizeF(10.5 if selected else 9.5)
            font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Medium)
            painter.setFont(font)
            colour = QColor(255, 255, 255) if selected else QColor(theme.current().text)
            colour.setAlpha(255 if selected else 170)
            painter.setPen(colour)
            room = (a.y() - b.y()) * 0.46
            text = painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, int(room))
            painter.drawText(QPointF(0, 4), text)
            painter.restore()

    def _paint_info(self, painter: QPainter) -> None:
        item = self._items[self._selected]
        polygon, side, _ = self._card(self._selected)
        box = polygon.boundingRect()
        width, height = 196.0, 112.0
        x = box.left() - width + 34 if box.left() - width + 34 > 12 else box.right() - 34
        x = max(12.0, min(x, self.width() - width - 12))
        rect = QRectF(x, box.center().y() - height / 2 + 6, width, height)
        painter.setPen(QPen(QColor(255, 255, 255, 190), 1))
        glass = QLinearGradient(rect.topLeft(), rect.bottomRight())
        glass.setColorAt(0, QColor(250, 252, 251, 240))
        glass.setColorAt(1, QColor(214, 244, 224, 226))
        painter.setBrush(glass)
        painter.drawRoundedRect(rect, 18, 18)
        ink = QColor(theme.INK)
        font = QFont(self.font())
        font.setPointSizeF(11.5)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(ink)
        title = painter.fontMetrics().elidedText(item.title, Qt.TextElideMode.ElideRight, int(width - 52))
        painter.drawText(QPointF(rect.left() + 16, rect.top() + 28), title)
        font.setPointSizeF(9)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor(0, 11, 26, 150))
        painter.drawText(QPointF(rect.left() + 16, rect.top() + 47), item.caption)
        font.setPointSizeF(24)
        font.setWeight(QFont.Weight.Light)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(QPointF(rect.left() + 16, rect.bottom() - 16), item.stat)
        painter.setPen(QPen(ink, 1.4))
        tip = QPointF(rect.right() - 18, rect.top() + 18)
        painter.drawLine(tip + QPointF(-9, 9), tip)
        painter.drawPolyline([tip + QPointF(-7, 0), tip, tip + QPointF(0, 7)])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 129, 60))
        painter.drawEllipse(QPointF(rect.right() - 20, rect.bottom() - 22), 4, 4)
