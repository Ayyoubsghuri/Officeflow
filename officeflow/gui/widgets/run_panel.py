"""Output folder, Preview/Run/Cancel, progress and results — shared by the
tool pages and the workflow builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMessageBox, QProgressBar, QVBoxLayout,
    QWidget,
)

from officeflow.core.operation import OperationContext, OperationResult, Preview
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, fill_table, label, make_table, open_folder
from officeflow.gui.worker import TaskThread

_TITLES = {"success": "Done", "warning": "Done — with remarks", "failed": "Could not complete",
           "cancelled": "Cancelled", "info": "Preview — nothing has been changed"}


class RunPanel(QWidget):
    previewRequested = Signal()
    runRequested = Signal()
    finished = Signal()

    def __init__(self, ctx: AppContext, run_text: str = "Run", with_preview: bool = True) -> None:
        super().__init__()
        self._ctx = ctx
        self._thread: TaskThread | None = None
        self.show_counts = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(label("Output folder", "field"))
        row = QHBoxLayout()
        self.output = QLineEdit(str(ctx.settings.resolved_output_dir()))
        browse = button("Browse", icon_name="folder")
        browse.clicked.connect(self._browse)
        row.addWidget(self.output, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        self.recursive = QCheckBox("Include files in sub-folders")
        self.recursive.setChecked(ctx.settings.include_subfolders)
        layout.addWidget(self.recursive)
        layout.addWidget(label("Results are written to this folder. Your original files are never "
                               "modified and existing files are never overwritten.", "help", wrap=True))

        actions = QHBoxLayout()
        self.preview_button = button("Preview", icon_name="eye",
                                     tooltip="See what would happen, without changing anything")
        self.run_button = button(run_text, "primary", "play")
        self.cancel_button = button("Cancel", "danger", "stop")
        self.cancel_button.setVisible(False)
        self.preview_button.setVisible(with_preview)
        self.preview_button.clicked.connect(self.previewRequested)
        self.run_button.clicked.connect(self.runRequested)
        self.cancel_button.clicked.connect(self.cancel)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setVisible(False)
        self.status = label("", "muted")
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

        self.banner = QFrame()
        banner_layout = QVBoxLayout(self.banner)
        banner_layout.setContentsMargins(16, 12, 16, 12)
        top = QHBoxLayout()
        self.banner_title = label("", "h2")
        self.open_button = button("Open output folder", icon_name="folder")
        self.open_button.clicked.connect(lambda: open_folder(self.output_dir()))
        top.addWidget(self.banner_title, 1)
        top.addWidget(self.open_button)
        banner_layout.addLayout(top)
        self.banner_text = label("", wrap=True)
        self.banner_notes = label("", "muted", wrap=True)
        banner_layout.addWidget(self.banner_text)
        banner_layout.addWidget(self.banner_notes)
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        self.table = make_table()
        self.table.setMinimumHeight(220)
        self.table.setVisible(False)
        layout.addWidget(self.table, 1)
        layout.addStretch()

    # -- public API ------------------------------------------------------
    def output_dir(self) -> Path:
        text = self.output.text().strip()
        return Path(text) if text else self._ctx.settings.resolved_output_dir()

    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, task: Callable[[OperationContext], Any], on_done: Callable[[Any], None],
              message: str = "Working…") -> None:
        """Run ``task`` in the background; ``on_done(result)`` is called in
        the GUI thread when it succeeds."""
        if self._thread is not None:
            return
        self.banner.setVisible(False)
        self.table.setVisible(False)
        self._set_busy(True, message)
        thread = TaskThread(task, self.output_dir(), self)
        thread.progress.connect(self._on_progress)
        thread.succeeded.connect(on_done)
        thread.failed.connect(lambda text: self.show_message("failed", text))
        thread.finished.connect(self._on_finished)
        self._thread = thread
        thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self._thread.cancel()
            self.status.setText("Cancelling…")

    def wait(self) -> None:
        """Block until the running task ends (used on shutdown and in tests)."""
        if self._thread is not None:
            self._thread.wait()

    def show_preview(self, preview: Preview) -> None:
        self._show("info", preview.summary, preview.warnings, [], preview.headers, preview.rows, False)

    def show_result(self, status: str, result: OperationResult) -> None:
        self._show(status, result.summary, result.warnings, result.errors, result.headers, result.rows,
                   status != "failed")

    def show_message(self, status: str, text: str) -> None:
        self._show(status, text, [], [], [], [], False)

    # -- internals -------------------------------------------------------
    def _show(self, status: str, summary: str, warnings: list[str], errors: list[str],
              headers: list[str], rows: list[list[str]], can_open: bool) -> None:
        self.banner.setProperty("banner", status)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner_title.setText(_TITLES.get(status, status))
        self.banner_text.setText(summary)
        notes = [f"✕ {e}" for e in errors if e != summary] + [f"• {w}" for w in warnings]
        extra = f"\n… and {len(notes) - 8} more (see Logs)" if len(notes) > 8 else ""
        self.banner_notes.setText("\n".join(notes[:8]) + extra)
        self.banner_notes.setVisible(bool(notes))
        self.open_button.setVisible(can_open)
        self.banner.setVisible(True)
        self.table.setVisible(bool(rows))
        if rows:
            fill_table(self.table, headers, rows)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.preview_button.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.bar.setVisible(busy)
        self.bar.setRange(0, 0)  # indeterminate until the first progress report
        self.status.setText(message)

    def _on_progress(self, done: int, total: int, message: str) -> None:
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(done)
        self.status.setText(f"{message}   ({done}/{total})" if total and self.show_counts else message)

    def _on_finished(self) -> None:
        self._thread = None
        self._set_busy(False)
        self.finished.emit()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose the output folder", str(self.output_dir()))
        if folder:
            self.output.setText(folder)

    def confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes
