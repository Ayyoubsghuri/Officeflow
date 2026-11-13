"""Home page: the fan of tools, the selected tool's folder and recent activity."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from officeflow.core import registry
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, card, fill_table, label, make_table, scrollable
from officeflow.gui.widgets.fan import FanItem, FolderFan
from officeflow.gui.widgets.folder_panel import BODY_TOP, FolderPanel

_STATUS = {"success": "Done", "warning": "Done with remarks", "failed": "Failed", "cancelled": "Cancelled"}


def format_when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y  %H:%M")
    except ValueError:
        return iso


class DashboardPage(QWidget):
    navigate = Signal(str)        # page key
    openTool = Signal(str)        # operation id

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._stats: dict[str, dict] = {}
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(36, 22, 36, 28)
        root.setSpacing(10)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for key in ("excel", "pdf", "word"):
            count = len(registry.by_category(key))
            chip = button(f"{registry.CATEGORIES[key]} ({count})", icon_name=key)
            chip.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            chips.addWidget(chip)
        chips.addStretch()
        for text, icon_name, key in (("History", "history", "history"), ("Logs", "logs", "logs"),
                                     ("New workflow", "plus", "workflow")):
            action = button(text, icon_name=icon_name)
            action.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            chips.addWidget(action)
        root.addLayout(chips)

        self.fan = FolderFan()
        self.fan.selectedChanged.connect(self._show_tool)
        self.fan.activated.connect(self.openTool)
        root.addWidget(self.fan)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)

        recent = card()
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(22, 18, 22, 18)
        recent_layout.addWidget(label("Recent activity", "h2"))
        recent_layout.addWidget(label("Everything runs on this computer, offline.", "muted"))
        self._empty = label("Nothing yet — processed tasks will be listed here.", "muted", wrap=True)
        self._recent = make_table()
        recent_layout.addWidget(self._empty)
        recent_layout.addWidget(self._recent, 1)
        recent_layout.addStretch()
        bottom.addWidget(recent, 4)

        self.folder = FolderPanel()
        folder_layout = QVBoxLayout(self.folder)
        folder_layout.setContentsMargins(26, BODY_TOP + 4, 26, 22)
        folder_layout.setSpacing(6)
        self._name = label("", "h2")
        self._about = label("", "muted", wrap=True)
        folder_layout.addWidget(self._name)
        folder_layout.addWidget(self._about)
        folder_layout.addSpacing(8)
        line = QHBoxLayout()
        self._line_left = label("Not used yet")
        self._line_right = label("")
        line.addWidget(self._line_left, 1)
        line.addWidget(self._line_right)
        folder_layout.addLayout(line)
        self._progress = QProgressBar()
        self._progress.setProperty("thin", "true")
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        folder_layout.addWidget(self._progress)
        folder_layout.addSpacing(8)
        self._last = label("", "muted", wrap=True)
        folder_layout.addWidget(self._last)
        folder_layout.addStretch()
        row = QHBoxLayout()
        self._open = button("Open tool", "hero", "arrow")
        self._open.clicked.connect(lambda: self.openTool.emit(self.fan.selected_id()))
        row.addWidget(self._open)
        row.addStretch()
        folder_layout.addLayout(row)
        bottom.addWidget(self.folder, 5)

        numbers = card()
        numbers_layout = QVBoxLayout(numbers)
        numbers_layout.setContentsMargins(22, 18, 22, 18)
        numbers_layout.setSpacing(4)
        numbers_layout.addWidget(label("Overview", "h2"))
        self._numbers: dict[str, QLabel] = {}
        for key, caption in (("runs", "Tasks run"), ("files", "Files processed"), ("rate", "Completed")):
            numbers_layout.addSpacing(6)
            numbers_layout.addWidget(label(caption, "caption"))
            value = label("0", "stat")
            self._numbers[key] = value
            numbers_layout.addWidget(value)
        numbers_layout.addStretch()
        bottom.addWidget(numbers, 2)
        root.addLayout(bottom, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(content))
        self.refresh()

    def refresh(self) -> None:
        db = self._ctx.db
        self._stats = db.target_stats()
        items = []
        for op in registry.all_operations():
            stat = self._stats.get(op.id)
            runs = stat["runs"] if stat else 0
            caption = f"{registry.CATEGORIES[op.category]} · {runs} run{'s' if runs != 1 else ''}"
            items.append(FanItem(op.id, op.name, caption, f"{round(100 * stat['ok'] / runs)}%" if runs else "New"))
        self.fan.set_items(items, self.fan.selected_id() or "pdf.organize")
        self._show_tool(self.fan.selected_id())

        totals = db.stats()
        self._numbers["runs"].setText(f"{totals['runs']:,}")
        self._numbers["files"].setText(f"{totals['files']:,}")
        self._numbers["rate"].setText(f"{round(100 * totals['ok'] / totals['runs'])}%" if totals["runs"] else "—")
        runs = db.list_runs(5)
        self._empty.setVisible(not runs)
        self._recent.setVisible(bool(runs))
        fill_table(self._recent, ["When", "Task", "Status"],
                   [[format_when(r.started_at), r.name, _STATUS.get(r.status, r.status)] for r in runs])

    def _show_tool(self, op_id: str) -> None:
        if not op_id:
            return
        op = registry.get(op_id)
        stat = self._stats.get(op_id)
        self._name.setText(op.name)
        self._about.setText(op.description)
        sheets = [e.lstrip(".").upper() for e in dict.fromkeys(op.input_extensions + op.output_extensions)]
        self.folder.set_sheets((sheets + ["Preview", "Report", "Log"])[:3])
        if stat:
            rate = round(100 * stat["ok"] / stat["runs"])
            self._line_left.setText(f"{stat['runs']} run(s) · last {format_when(stat['started_at'])}")
            self._line_right.setText(f"{rate}% completed")
            self._progress.setValue(rate)
            self._last.setText(stat["summary"])
        else:
            self._line_left.setText("Not used yet")
            self._line_right.setText("")
            self._progress.setValue(0)
            self._last.setText("Open the tool, add your files and preview the result before running it.")
