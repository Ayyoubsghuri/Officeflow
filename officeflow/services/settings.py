"""User settings persisted as a small JSON file."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from officeflow.services import paths

log = logging.getLogger(__name__)


@dataclass
class Settings:
    theme: str = "dark"  # "dark" | "light"
    output_dir: str = ""
    include_subfolders: bool = True
    last_input_dir: str = ""
    ai_model: str = "claude-opus-5-5"
    ai_redact: bool = True           # replace file paths / e-mails in AI requests

    def resolved_output_dir(self) -> Path:
        return Path(self.output_dir) if self.output_dir else paths.default_output_dir()

    @classmethod
    def load(cls, file: Path | None = None) -> "Settings":
        file = file or paths.settings_file()
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            log.warning("Settings file is unreadable; using defaults")
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, file: Path | None = None) -> None:
        file = file or paths.settings_file()
        file.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
