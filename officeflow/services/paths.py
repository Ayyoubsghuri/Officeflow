"""Where OfficeFlow keeps its own data (settings, database, logs, plugins)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_home() -> Path:
    """Per-user data folder. ``OFFICEFLOW_HOME`` overrides it (used by tests
    and portable installs)."""
    override = os.environ.get("OFFICEFLOW_HOME")
    if override:
        home = Path(override)
    elif sys.platform == "win32":
        home = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "OfficeFlow"
    elif sys.platform == "darwin":
        home = Path.home() / "Library" / "Application Support" / "OfficeFlow"
    else:
        home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "officeflow"
    home.mkdir(parents=True, exist_ok=True)
    return home


def settings_file() -> Path:
    return app_home() / "settings.json"


def database_file() -> Path:
    return app_home() / "officeflow.db"


def log_file() -> Path:
    folder = app_home() / "logs"
    folder.mkdir(exist_ok=True)
    return folder / "officeflow.log"


def plugins_dir() -> Path:
    folder = app_home() / "plugins"
    folder.mkdir(exist_ok=True)
    return folder


def default_output_dir() -> Path:
    return Path.home() / "Documents" / "OfficeFlow Output"
