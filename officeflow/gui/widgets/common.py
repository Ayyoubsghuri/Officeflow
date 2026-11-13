"""Small building blocks used across pages."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from officeflow.gui import icons, theme


def label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, kind: str = "", icon_name: str = "", tooltip: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        widget.setProperty("kind", kind)
    if icon_name:
        color = theme.INK if kind in ("primary", "hero") else theme.DANGER if kind == "danger" else None
        widget.setIcon(icons.icon(icon_name, color, 18))
        widget.setIconSize(QSize(18, 18))
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def card(kind: str = "true") -> QFrame:
    frame = QFrame()
    frame.setProperty("card", kind)
    return frame


def scrollable(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area


def page_header(title: str, subtitle: str = "") -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(label(title, "h1"))
    if subtitle:
        layout.addWidget(label(subtitle, "muted", wrap=True))
    return box


def open_folder(path: Path | str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def fill_table(table: QTableWidget, headers: list[str], rows: list[list[str]], limit: int = 2000) -> None:
    """Show ``rows`` (at most ``limit``, to keep the window responsive)."""
    table.setSortingEnabled(False)
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    shown = rows[:limit]
    table.setRowCount(len(shown))
    for r, row in enumerate(shown):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    for column in range(len(headers)):
        table.setColumnWidth(column, min(table.columnWidth(column) + 16, 360))
    table.horizontalHeader().setStretchLastSection(True)


def make_table() -> QTableWidget:
    table = QTableWidget()
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setWordWrap(False)
    return table


class ClickableCard(QFrame):
    clicked = Signal()

    def __init__(self, kind: str = "tool") -> None:
        super().__init__()
        self.setProperty("card", kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def tool_card(icon_name: str, title: str, description: str, badge: str = "") -> ClickableCard:
    frame = ClickableCard()
    frame.setMinimumHeight(132)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(8)
    top = QHBoxLayout()
    picture = QLabel()
    picture.setPixmap(icons.pixmap(icon_name, theme.current().accent_text, 24))
    top.addWidget(picture)
    top.addStretch()
    if badge:
        top.addWidget(label(badge, "badge"))
    else:
        arrow = QLabel()
        arrow.setPixmap(icons.pixmap("arrow", theme.current().muted, 18))
        top.addWidget(arrow)
    layout.addLayout(top)
    layout.addWidget(label(title, "h2", wrap=True))
    layout.addWidget(label(description, "muted", wrap=True))
    layout.addStretch()
    return frame
