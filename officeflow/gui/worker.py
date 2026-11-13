"""Background execution so the window never freezes."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from officeflow.core.operation import Cancelled, OperationContext, OperationError

log = logging.getLogger(__name__)


class TaskThread(QThread):
    """Runs ``task(ctx)`` off the GUI thread and reports through signals."""

    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[OperationContext], Any], output_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._task = task
        self._cancel = threading.Event()
        self._ctx = OperationContext(output_dir, self.progress.emit, self._cancel)

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # executed in the worker thread
        try:
            self.succeeded.emit(self._task(self._ctx))
        except Cancelled:
            self.failed.emit("Cancelled.")
        except OperationError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Background task crashed")
            self.failed.emit(f"Unexpected error: {exc.__class__.__name__}: {exc}")
