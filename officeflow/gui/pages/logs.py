"""Log viewer for troubleshooting."""

from __future__ import annotations

from collections import deque

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from officeflow.services import paths
from officeflow.gui.widgets.common import button, open_folder, page_header

_FILTERS = (("All messages", ()), ("Warnings and errors", ("WARNING", "ERROR", "CRITICAL")),
            ("Errors only", ("ERROR", "CRITICAL")))


class LogsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(16)
        head = QHBoxLayout()
        head.addWidget(page_header("Logs and Error Reports", "Technical details of what the application did. "
                                   "Send this to your administrator if something goes wrong."), 1)
        self._filter = QComboBox()
        for text, _ in _FILTERS:
            self._filter.addItem(text)
        self._filter.currentIndexChanged.connect(self.refresh)
        refresh = button("Refresh", icon_name="refresh")
        folder = button("Open log folder", icon_name="folder")
        refresh.clicked.connect(self.refresh)
        folder.clicked.connect(lambda: open_folder(paths.log_file().parent))
        for widget in (self._filter, refresh, folder):
            head.addWidget(widget)
        root.addLayout(head)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setProperty("mono", "true")
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self._view, 1)
        self.refresh()

    def refresh(self) -> None:
        levels = _FILTERS[self._filter.currentIndex()][1]
        lines: deque[str] = deque(maxlen=1000)
        keep = True
        try:
            with open(paths.log_file(), encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line[:4].isdigit():  # a new record; continuation lines follow their record
                        keep = not levels or any(f"  {level} " in line[:40] for level in levels)
                    if keep:
                        lines.append(line.rstrip("\n"))
        except FileNotFoundError:
            pass
        self._view.setPlainText("\n".join(lines) or "No log entries.")
        bar = self._view.verticalScrollBar()
        bar.setValue(bar.maximum())
