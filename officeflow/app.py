"""Application bootstrap: wires services, registry and the GUI together."""

from __future__ import annotations

import logging
import sys

from officeflow import APP_NAME, __version__
from officeflow.core import registry
from officeflow.services import paths
from officeflow.services.database import Database
from officeflow.services.logsetup import setup_logging
from officeflow.services.settings import Settings

log = logging.getLogger("officeflow.app")


def create(argv: list[str] | None = None):
    """Build the QApplication and main window (separate from ``run`` so tests
    can create the window without entering the event loop)."""
    from PySide6.QtWidgets import QApplication

    from officeflow.gui import theme
    from officeflow.gui.context import AppContext
    from officeflow.gui.main_window import MainWindow

    setup_logging()
    log.info("Starting %s %s", APP_NAME, __version__)
    registry.load_builtin()
    for problem in registry.load_plugins(paths.plugins_dir()):
        log.error("Plugin not loaded: %s", problem)

    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    ctx = AppContext(Settings.load(), Database())
    family = theme.load_font()
    theme.apply(app, ctx.settings.theme, family)
    window = MainWindow(ctx)
    window.themeChanged.connect(lambda name: theme.apply(app, name, family))
    return app, window


def run() -> int:
    app, window = create()
    window.show()
    return app.exec()
