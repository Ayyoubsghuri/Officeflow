"""Input selection: drag-and-drop list of files and folders."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from officeflow.gui import icons, theme
from officeflow.gui.context import AppContext
from officeflow.gui.widgets.common import button, label


class _DropList(QListWidget):
    dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setMinimumHeight(150)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            self.dropped.emit([Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)  # internal move = reorder

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(theme.current().muted))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                             "Drop files or folders here\nor use the buttons below")
            painter.end()


class InputList(QWidget):
    """Lets the user gather files and folders. Order is kept (drag to reorder)."""

    changed = Signal()

    def __init__(self, ctx: AppContext, title: str, extensions: Sequence[str]) -> None:
        super().__init__()
        self._ctx = ctx
        self._extensions = tuple(extensions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._title = label(title, "field", wrap=True)
        layout.addWidget(self._title)
        self._list = _DropList()
        self._list.dropped.connect(self.add_paths)
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        add_files = button("Files", icon_name="plus", tooltip="Add files")
        add_folder = button("Folder", icon_name="folder", tooltip="Add a folder")
        remove = button("", "ghost", "minus", "Remove the selected entries from the list")
        clear = button("", "ghost", "trash", "Clear the list")
        add_files.clicked.connect(self._browse_files)
        add_folder.clicked.connect(self._browse_folder)
        remove.clicked.connect(self._remove_selected)
        clear.clicked.connect(self.clear)
        for widget in (add_files, add_folder):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(remove)
        row.addWidget(clear)
        layout.addLayout(row)

    def set_filter(self, title: str, extensions: Sequence[str]) -> None:
        self._title.setText(title)
        self._extensions = tuple(extensions)

    def paths(self) -> list[Path]:
        return [Path(self._list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self._list.count())]

    def add_paths(self, paths: Sequence[Path]) -> None:
        existing = set(self.paths())
        for path in paths:
            path = Path(path)
            if path in existing or not path.exists():
                continue
            if path.is_file() and self._extensions and path.suffix.lower() not in self._extensions:
                continue
            item = QListWidgetItem(icons.icon("folder" if path.is_dir() else "pdf", theme.current().muted, 18),
                                   str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self._list.addItem(item)
            existing.add(path)
        self.changed.emit()

    def clear(self) -> None:
        self._list.clear()
        self.changed.emit()

    def _remove_selected(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))
        self.changed.emit()

    def _start_dir(self) -> str:
        return self._ctx.settings.last_input_dir or str(Path.home())

    def _remember(self, folder: Path) -> None:
        self._ctx.settings.last_input_dir = str(folder)
        self._ctx.settings.save()

    def _browse_files(self) -> None:
        pattern = " ".join(f"*{e}" for e in self._extensions) or "*"
        files, _ = QFileDialog.getOpenFileNames(self, "Choose files", self._start_dir(),
                                                f"Supported files ({pattern});;All files (*)")
        if files:
            self._remember(Path(files[0]).parent)
            self.add_paths([Path(f) for f in files])

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder", self._start_dir())
        if folder:
            self._remember(Path(folder))
            self.add_paths([Path(folder)])
