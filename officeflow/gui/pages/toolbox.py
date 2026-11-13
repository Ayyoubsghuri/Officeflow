"""A category of tools shown as cards; clicking one opens its tool page."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QStackedWidget, QVBoxLayout, QWidget

from officeflow.core import registry
from officeflow.gui.context import AppContext
from officeflow.gui.pages.tool_page import ToolPage
from officeflow.gui.widgets.common import card, label, page_header, scrollable, tool_card

_INTRO = {
    "excel": "Merge, clean, split, compare and convert Excel and CSV files — one file or whole folders.",
    "pdf": "Organise, rename, split, merge and search large collections of PDF documents.",
    "word": "Generate and edit Word documents in bulk.",
}


class ToolboxPage(QWidget):
    def __init__(self, ctx: AppContext, category: str) -> None:
        super().__init__()
        self._ctx = ctx
        self._pages: dict[str, ToolPage] = {}
        self._stack = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        grid_page = QWidget()
        grid_page.setObjectName("page")
        layout = QVBoxLayout(grid_page)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(22)
        operations = registry.by_category(category)
        layout.addWidget(page_header(f"{registry.CATEGORIES[category]} Toolbox", _INTRO.get(category, "")))
        if operations:
            grid = QGridLayout()
            grid.setSpacing(16)
            for index, op in enumerate(operations):
                tile = tool_card(category, op.name, op.description)
                tile.clicked.connect(lambda op_id=op.id: self.open_tool(op_id))
                grid.addWidget(tile, index // 3, index % 3)
            for column in range(3):
                grid.setColumnStretch(column, 1)
            layout.addLayout(grid)
        else:
            empty = card()
            box = QVBoxLayout(empty)
            box.setContentsMargins(28, 26, 28, 26)
            box.addWidget(label("Not available yet", "h2"))
            box.addWidget(label(
                f"{registry.CATEGORIES[category]} tools are planned for a later development phase. "
                "They will appear here automatically once they are installed.", "muted", wrap=True))
            layout.addWidget(empty)
        layout.addStretch()
        self._stack.addWidget(scrollable(grid_page))

    def open_tool(self, op_id: str) -> None:
        if op_id not in self._pages:
            page = ToolPage(self._ctx, registry.get(op_id))
            page.back.connect(lambda: self._stack.setCurrentIndex(0))
            self._pages[op_id] = page
            self._stack.addWidget(page)
        self._stack.setCurrentWidget(self._pages[op_id])

    def show_grid(self) -> None:
        self._stack.setCurrentIndex(0)
