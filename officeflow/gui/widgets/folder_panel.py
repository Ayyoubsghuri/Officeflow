"""Green "open folder" panel with glass documents peeking out of it."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame

TAB_TOP = 66      # y of the folder tab
BODY_TOP = 98     # y where the front of the folder starts


class FolderPanel(QFrame):
    """Children are laid out on the front of the folder; set the layout's top
    margin to at least ``BODY_TOP``."""

    def __init__(self) -> None:
        super().__init__()
        self._sheets = ["Excel", "PDF", "Report"]
        self.setProperty("folder", "true")
        self.setMinimumHeight(330)

    def set_sheets(self, names: list[str]) -> None:
        self._sheets = names[:3]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = float(self.width()), float(self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#15633A"))
        painter.drawRoundedRect(QRectF(0, 0, width, height), 24, 24)

        font = QFont(self.font())
        for index, name in enumerate(self._sheets):
            sheet = QRectF(width * (0.24 + 0.17 * index), 44 - index * 12, width * 0.36, 150)
            glass = QLinearGradient(sheet.topLeft(), sheet.bottomRight())
            glass.setColorAt(0, QColor(255, 255, 255, 70 + index * 22))
            glass.setColorAt(1, QColor(255, 255, 255, 26 + index * 10))
            painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
            painter.setBrush(glass)
            painter.drawRoundedRect(sheet, 16, 16)
            font.setPointSizeF(8.5)
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 215))
            painter.drawText(QPointF(sheet.left() + 14, sheet.top() + 22), name)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 90))
            for row in range(2):
                painter.drawRoundedRect(QRectF(sheet.left() + 14, sheet.top() + 34 + row * 10,
                                               sheet.width() * (0.5 - row * 0.15), 3.5), 2, 2)

        radius = 24.0
        front = QPainterPath(QPointF(0, TAB_TOP + radius))
        front.quadTo(QPointF(0, TAB_TOP), QPointF(radius, TAB_TOP))
        front.lineTo(width * 0.27, TAB_TOP)
        front.cubicTo(QPointF(width * 0.37, TAB_TOP), QPointF(width * 0.36, BODY_TOP), QPointF(width * 0.47, BODY_TOP))
        front.lineTo(width - radius, BODY_TOP)
        front.quadTo(QPointF(width, BODY_TOP), QPointF(width, BODY_TOP + radius))
        front.lineTo(width, height - radius)
        front.quadTo(QPointF(width, height), QPointF(width - radius, height))
        front.lineTo(radius, height)
        front.quadTo(QPointF(0, height), QPointF(0, height - radius))
        front.closeSubpath()
        body = QLinearGradient(0, TAB_TOP, width, height)
        body.setColorAt(0, QColor("#43A869"))
        body.setColorAt(0.55, QColor("#3A9E60"))
        body.setColorAt(1, QColor("#55BD7A"))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(body)
        painter.drawPath(front)
        painter.end()
