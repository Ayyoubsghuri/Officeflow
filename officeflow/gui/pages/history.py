"""Processing history (from the local database)."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from officeflow.gui.context import AppContext
from officeflow.gui.pages.dashboard import _STATUS, format_when
from officeflow.gui.widgets.common import button, card, fill_table, label, make_table, open_folder, page_header


class HistoryPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.setObjectName("page")
        self._ctx = ctx
        self._runs = []
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(16)
        head = QHBoxLayout()
        head.addWidget(page_header("Processing History", "Every task that was run, with its result."), 1)
        self._open = button("Open output folder", icon_name="folder")
        refresh = button("Refresh", icon_name="refresh")
        clear = button("Clear history", "danger", "trash")
        self._open.clicked.connect(self._open_selected)
        refresh.clicked.connect(self.refresh)
        clear.clicked.connect(self._clear)
        for widget in (self._open, refresh, clear):
            head.addWidget(widget)
        root.addLayout(head)
        self._table = make_table()
        self._table.itemSelectionChanged.connect(self._show_details)
        root.addWidget(self._table, 3)
        box = card()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.addWidget(label("Details", "caption"))
        self._details = label("Select a task to see its warnings and errors.", "muted", wrap=True)
        layout.addWidget(self._details)
        root.addWidget(box, 1)
        self.refresh()

    def refresh(self) -> None:
        self._runs = self._ctx.db.list_runs(500)
        fill_table(self._table, ["When", "Task", "Status", "Files in", "Files out", "Seconds", "Result"], [
            [format_when(r.started_at), r.name, _STATUS.get(r.status, r.status), r.input_count,
             r.output_count, f"{r.duration_s:.1f}", r.summary] for r in self._runs])
        self._open.setEnabled(False)

    def _selected(self):
        row = self._table.currentRow()
        return self._runs[row] if 0 <= row < len(self._runs) else None

    def _show_details(self) -> None:
        run = self._selected()
        self._open.setEnabled(run is not None)
        if run is None:
            return
        lines = [f"Output folder: {run.output_dir}"]
        for step in run.details.get("steps", []):
            lines.append(f"{step['name']}: {step['summary']}")
        nested = [m for step in run.details.get("steps", []) for m in step.get("errors", []) + step.get("warnings", [])]
        notes = [f"✕ {e}" for e in run.details.get("errors", [])] + [f"• {w}" for w in run.details.get("warnings", [])]
        notes += [f"• {m}" for m in nested]
        lines += notes[:12] or ["No warnings or errors."]
        if len(notes) > 12:
            lines.append(f"… and {len(notes) - 12} more")
        self._details.setText("\n".join(lines))

    def _open_selected(self) -> None:
        run = self._selected()
        if run:
            open_folder(run.output_dir)

    def _clear(self) -> None:
        if QMessageBox.question(self, "Clear history?", "Remove all entries from the history? "
                                "Your files are not affected.") == QMessageBox.StandardButton.Yes:
            self._ctx.db.clear_runs()
            self.refresh()
