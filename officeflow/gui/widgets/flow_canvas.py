"""Node canvas for the Workflow Builder.

A dotted canvas where the workflow is drawn as cards joined by curved
connectors: a start node ("Files & folders"), one node per step, and a dashed
"Add step" node at the end. Nodes can be dragged; the view pans by dragging
the background and zooms with the wheel. The canvas only *shows* the workflow:
the page owns the steps and rebuilds the scene after every change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QVBoxLayout,
)

from officeflow.gui import icons, theme
from officeflow.gui.widgets.common import button

NODE_W, NODE_H = 316.0, 104.0
GHOST_W, GHOST_H = 200.0, 64.0
PINK = QColor("#F2557D")
START_ID = "start"
GHOST_ID = "add"

# Icon tile colour per node kind (background, icon colour).
TILES = {
    "start": ("#E3F25C", theme.INK),
    "excel": ("#68E78E", theme.INK),
    "pdf": ("#4F8DF7", theme.INK),
    "word": ("#B79CFF", theme.INK),
    "cross": ("#FFB547", theme.INK),
}
STATUS = {  # chip text colour / background
    "success": ("Done", "#12813C", "#D7F7E1"),
    "warning": ("Done · remarks", "#8A5A00", "#FFF0C7"),
    "failed": ("Failed", "#C0151A", "#FFD9DA"),
    "cancelled": ("Cancelled", "#5A6472", "#E6E9ED"),
    "running": ("Running…", "#B0185A", "#FFE0EC"),
    "pending": ("Not run", "#5A6472", "#E6E9ED"),
}


def _colors() -> dict[str, QColor]:
    dark = theme.current().name == "dark"
    return {
        "canvas": QColor("#0C0D0F" if dark else "#FAFAFA"),
        "dot": QColor(255, 255, 255, 30) if dark else QColor(0, 11, 26, 46),
        "card": QColor("#17191C" if dark else "#FFFFFF"),
        "border": QColor("#2C3034" if dark else "#E1E4E8"),
        "text": QColor("#F4F6F8" if dark else "#0B0D10"),
        "muted": QColor("#8A93A2" if dark else "#5A6472"),
        "shadow": QColor(0, 0, 0, 90 if dark else 18),
        "chip": QColor("#262A2E" if dark else "#F1F3F5"),
    }


@dataclass
class NodeData:
    key: str                 # START_ID or the step's uid
    kind: str                # "start" or an operation category
    icon: str
    chip: str                # small tag above the title ("Start", "Step 2 · PDF")
    title: str
    subtitle: str
    status: str = ""         # key of STATUS, empty = no run yet
    status_text: str = ""    # e.g. "12 files"
    warning: str = ""        # shown when the step cannot follow the previous one
    chip_lime: bool = False
    extra: dict = field(default_factory=dict)


class NodeItem(QGraphicsObject):
    moved = Signal()

    def __init__(self, data: NodeData) -> None:
        super().__init__()
        self.data_ = data
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.setZValue(2)
        self.size = (NODE_W, NODE_H)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-8, -8, NODE_W + 16, NODE_H + 20)

    def in_port(self) -> QPointF:
        return self.pos() + QPointF(0, NODE_H / 2)

    def out_port(self) -> QPointF:
        return self.pos() + QPointF(NODE_W, NODE_H / 2)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.moved.emit()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        c = _colors()
        d = self.data_
        rect = QRectF(0, 0, NODE_W, NODE_H)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(c["shadow"])
        painter.drawRoundedRect(rect.translated(0, 6), 22, 22)
        border = PINK if self.isSelected() else (c["muted"] if self._hover else c["border"])
        if d.warning:
            border = QColor("#FF1F22")
        painter.setPen(QPen(border, 2 if self.isSelected() or d.warning else 1.2))
        painter.setBrush(c["card"])
        painter.drawRoundedRect(rect, 22, 22)

        tile_colour, icon_colour = TILES.get(d.kind, TILES["cross"])
        tile = QRectF(18, (NODE_H - 60) / 2, 60, 60)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tile_colour))
        painter.drawRoundedRect(tile, 16, 16)
        glyph = icons.pixmap(d.icon, icon_colour, 30)
        painter.drawPixmap(QRectF(tile.center().x() - 15, tile.center().y() - 15, 30, 30), glyph,
                           QRectF(glyph.rect()))

        x = tile.right() + 16
        width = NODE_W - x - 16
        font = QFont(painter.font())
        # unhinted glyphs keep the same width at every zoom level, so measured
        # text matches what is drawn on the scaled canvas
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        chip_text = d.chip
        metrics = QFontMetrics(font)
        chip_w = min(metrics.horizontalAdvance(chip_text) * 1.08 + 18, width)
        chip = QRectF(x, 16, chip_w, 22)
        painter.setBrush(QColor("#E3F25C") if d.chip_lime else c["chip"])
        painter.drawRoundedRect(chip, 6, 6)
        painter.setPen(QColor(theme.INK) if d.chip_lime else c["muted"])
        painter.drawText(chip.adjusted(8, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(chip_text, Qt.TextElideMode.ElideRight, int(chip_w - 12)))
        if d.status:
            label, ink, bg = STATUS[d.status]
            text = f"{label} · {d.status_text}" if d.status_text else label
            status_w = min(metrics.horizontalAdvance(text) * 1.08 + 18, width - chip_w - 6)
            if status_w > 30:
                status = QRectF(chip.right() + 6, 16, status_w, 22)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(bg))
                painter.drawRoundedRect(status, 6, 6)
                painter.setPen(QColor(ink))
                painter.drawText(status.adjusted(8, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter,
                                 metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(status_w - 12)))

        font.setPixelSize(18)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(c["text"])
        metrics = QFontMetrics(font)
        painter.drawText(QPointF(x, 64), metrics.elidedText(d.title, Qt.TextElideMode.ElideRight, int(width)))
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor("#FF1F22") if d.warning else c["muted"])
        metrics = QFontMetrics(font)
        sub = d.warning or d.subtitle
        painter.drawText(QPointF(x, 86), metrics.elidedText(sub, Qt.TextElideMode.ElideRight, int(width)))



class GhostItem(QGraphicsObject):
    """Dashed "+ Add step" node at the end of the chain."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.size = (GHOST_W, GHOST_H)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-4, -4, GHOST_W + 8, GHOST_H + 8)

    def in_port(self) -> QPointF:
        return self.pos() + QPointF(0, GHOST_H / 2)

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self.boundingRect().contains(event.pos()):
            self.clicked.emit()

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        c = _colors()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(PINK if self._hover else c["muted"], 1.4, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QColor(PINK.red(), PINK.green(), PINK.blue(), 22) if self._hover else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0, 0, GHOST_W, GHOST_H), 18, 18)
        font = QFont(painter.font())
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(PINK)
        painter.drawText(QRectF(0, 0, GHOST_W, GHOST_H), Qt.AlignmentFlag.AlignCenter, "+  Add step")


class EdgeItem(QGraphicsPathItem):
    """Curved connector with ring ports at both ends.

    When the next node is clearly to the right, the curve leaves from the
    right side; when the nodes overlap horizontally (the staggered layout), it
    leaves from the top or bottom edge and bends into the target's left port.
    """

    def __init__(self, source, target, broken: bool = False) -> None:
        super().__init__()
        self.source, self.target, self.broken = source, target, broken
        self._colour = QColor("#FF1F22") if broken else PINK
        dashed = broken or isinstance(target, GhostItem)
        pen = QPen(self._colour, 2.2, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(3)
        self._ends = (QPointF(), QPointF())
        self.refresh()

    def refresh(self) -> None:
        self.prepareGeometryChange()
        sp, (sw, sh) = self.source.pos(), self.source.size
        tp, (_tw, th) = self.target.pos(), self.target.size
        end = QPointF(tp.x(), tp.y() + th / 2)
        path = QPainterPath()
        if tp.x() >= sp.x() + sw + 40:
            start = QPointF(sp.x() + sw, sp.y() + sh / 2)
            span = max((end.x() - start.x()) * 0.5, 40)
            path.moveTo(start)
            path.cubicTo(start + QPointF(span, 0), end - QPointF(span, 0), end)
        else:
            below = end.y() > sp.y() + sh / 2
            start = QPointF(sp.x() + sw * 0.40, sp.y() + (sh if below else 0))
            path.moveTo(start)
            path.cubicTo(QPointF(start.x(), end.y()), QPointF(start.x() + (end.x() - start.x()) * 0.25, end.y()), end)
        self._ends = (start, end)
        self.setPath(path)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return super().boundingRect().adjusted(-10, -10, 10, 10)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        super().paint(painter, option, widget)
        painter.setPen(QPen(self._colour, 2))
        painter.setBrush(_colors()["card"])
        for point in self._ends:
            painter.drawEllipse(point, 6.5, 6.5)


class FlowScene(QGraphicsScene):
    nodeSelected = Signal(str)     # node key ("" when nothing is selected)
    addRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.nodes: dict[str, NodeItem] = {}
        self.ghost: GhostItem | None = None
        self.edges: list[EdgeItem] = []
        self.positions: dict[str, QPointF] = {}
        self.selectionChanged.connect(self._selection)
        self._building = False

    def build(self, nodes: list[NodeData], broken: set[str], selected: str = "") -> None:
        """Replace the scene content. Node positions survive rebuilds."""
        self._building = True
        for node in self.nodes.values():
            self.positions[node.data_.key] = node.pos()
        self.clear()
        self.nodes, self.edges = {}, []
        previous = None
        for index, data in enumerate(nodes):
            item = NodeItem(data)
            item.setPos(self.positions.get(data.key, self.default_position(index)))
            item.moved.connect(self.refresh_edges)
            self.addItem(item)
            self.nodes[data.key] = item
            if previous is not None:
                self.addItem(self._edge(previous, item, data.key in broken))
            previous = item
        self.ghost = GhostItem()
        self._place_ghost()
        self.ghost.clicked.connect(self.addRequested)
        self.addItem(self.ghost)
        if previous is not None:
            self.addItem(self._edge(previous, self.ghost, False))
        if selected in self.nodes:
            self.nodes[selected].setSelected(True)
        self._building = False
        self.setSceneRect(self.itemsBoundingRect().adjusted(-2000, -2000, 2000, 2000))

    def _edge(self, source, target, broken: bool) -> EdgeItem:
        edge = EdgeItem(source, target, broken)
        self.edges.append(edge)
        return edge

    STEP_X, STEP_Y = 250.0, 170.0

    @classmethod
    def default_position(cls, index: int) -> QPointF:
        """Staggered flow: each node sits to the right of the previous one,
        alternately below and above it, so the chain stays compact."""
        return QPointF(index * cls.STEP_X, (index % 2) * cls.STEP_Y)

    def _place_ghost(self) -> None:
        if not self.ghost or not self.nodes:
            return
        count = len(self.nodes)
        last = list(self.nodes.values())[-1]
        step = self.default_position(count) - self.default_position(count - 1)
        self.ghost.setPos(last.pos() + step + QPointF(0, (NODE_H - GHOST_H) / 2))

    def tidy(self) -> None:
        self.positions = {}
        for index, node in enumerate(self.nodes.values()):
            node.setPos(self.default_position(index))
        self.refresh_edges()

    def refresh_edges(self) -> None:
        self._place_ghost()
        for edge in self.edges:
            edge.refresh()

    def select(self, key: str) -> None:
        self.clearSelection()
        if key in self.nodes:
            self.nodes[key].setSelected(True)

    def _selection(self) -> None:
        if self._building:
            return
        chosen = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        self.nodeSelected.emit(chosen[0].data_.key if chosen else "")


class FlowView(QGraphicsView):
    """Dotted, pannable, zoomable view with floating tool bars."""

    def __init__(self, scene: FlowScene) -> None:
        super().__init__(scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(420)

        # left tool bar: fit / zoom in / zoom out, then layout tools
        self.zoom_bar = self._bar(vertical=True)
        self.fit_button = self._tool(self.zoom_bar, "fit", "Fit the workflow in view", self.fit)
        self._tool(self.zoom_bar, "plus", "Zoom in", lambda: self.zoom(1.2))
        self._tool(self.zoom_bar, "minus", "Zoom out", lambda: self.zoom(1 / 1.2))
        self.layout_bar = self._bar(vertical=True)
        self.tidy_button = self._tool(self.layout_bar, "tidy", "Tidy up the layout", lambda: (scene.tidy(), self.fit()))

        # bottom tool bar: create, undo, redo
        self.bottom_bar = self._bar(vertical=False)
        self.create_button = button("Add step", "create", "sparkle")
        self.bottom_bar.layout().addWidget(self.create_button)
        self.undo_button = self._tool(self.bottom_bar, "undo", "Undo", None)
        self.redo_button = self._tool(self.bottom_bar, "redo", "Redo", None)

    # -- overlay tool bars -----------------------------------------------
    def _bar(self, vertical: bool) -> QFrame:
        bar = QFrame(self)
        bar.setProperty("floatbar", "true")
        layout = QVBoxLayout(bar) if vertical else QHBoxLayout(bar)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        return bar

    def _tool(self, bar: QFrame, icon_name: str, tip: str, slot):
        widget = button("", "tool", icon_name, tip)
        widget.setFixedSize(40, 40)
        if slot:
            widget.clicked.connect(slot)
        bar.layout().addWidget(widget)
        return widget

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for bar in (self.zoom_bar, self.layout_bar, self.bottom_bar):
            bar.adjustSize()
        self.zoom_bar.move(18, 18)
        self.layout_bar.move(18, 18 + self.zoom_bar.height() + 12)
        self.bottom_bar.move((self.width() - self.bottom_bar.width()) // 2,
                             self.height() - self.bottom_bar.height() - 18)

    # -- navigation --------------------------------------------------------
    def zoom(self, factor: float) -> None:
        current = self.transform().m11()
        factor = max(0.35 / current, min(factor, 1.8 / current))
        self.scale(factor, factor)

    def fit(self) -> None:
        items = self.scene().itemsBoundingRect()
        if items.isEmpty():
            return
        area = QRectF(items).adjusted(-90, -70, 90, 110)        # room for the floating bars
        viewport = self.viewport().rect()
        scale = min(viewport.width() / area.width(), viewport.height() / area.height())
        scale = max(0.72, min(scale, 1.0))                      # never too small to read
        self.resetTransform()
        self.scale(scale, scale)
        visible_w = viewport.width() / scale
        if area.width() <= visible_w:
            self.centerOn(area.center())
        else:                                                    # too wide: start from the left
            self.centerOn(QPointF(area.left() + visible_w / 2, area.center().y()))

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta:
            self.zoom(1.12 if delta > 0 else 1 / 1.12)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        c = _colors()
        painter.fillRect(rect, c["canvas"])
        step = 24
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(c["dot"]))
        size = 1.6 / max(self.transform().m11(), 0.5)
        y = top
        while y < rect.bottom():
            x = left
            while x < rect.right():
                painter.drawEllipse(QPointF(x, y), size, size)
                x += step
            y += step
