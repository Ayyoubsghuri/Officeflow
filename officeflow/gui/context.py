"""Objects shared by all pages."""

from __future__ import annotations

from dataclasses import dataclass

from officeflow.services.database import Database
from officeflow.services.settings import Settings


@dataclass
class AppContext:
    settings: Settings
    db: Database
