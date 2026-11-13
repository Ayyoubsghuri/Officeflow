"""Application logging: a rotating UTF-8 log file plus the console."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from officeflow.services import paths

FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"


def setup_logging(file: Path | None = None, level: int = logging.INFO) -> Path:
    file = file or paths.log_file()
    root = logging.getLogger("officeflow")
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    file_handler = RotatingFileHandler(file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(console)
    return file
