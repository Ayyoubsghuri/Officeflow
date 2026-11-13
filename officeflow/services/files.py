"""Unicode-safe file helpers shared by every engine."""

from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_INVISIBLE = re.compile(r"[​-‏‪-‮⁦-⁩؜﻿]")
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{n}{i}" for n in ("COM", "LPT") for i in range(1, 10)}


def safe_filename(name: str, replacement: str = "-", max_length: int = 150) -> str:
    """Make ``name`` valid on Windows, macOS and Linux while keeping Arabic and
    accented characters intact. ``2024/01/005`` becomes ``2024-01-005``."""
    name = unicodedata.normalize("NFC", str(name))
    name = _INVISIBLE.sub("", name)
    name = _INVALID_CHARS.sub(replacement, name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > max_length:
        name = name[:max_length].rstrip(" .")
    if not name:
        return "_"
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name


def unique_path(path: Path, taken: set[Path] | None = None) -> Path:
    """Return ``path`` or, if it exists (on disk or in ``taken``), the first
    free ``name (2).ext`` variant. The result is added to ``taken``."""
    candidate = path
    counter = 2
    while candidate.exists() or (taken is not None and candidate in taken):
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        counter += 1
    if taken is not None:
        taken.add(candidate)
    return candidate


def collect_files(
    paths: Iterable[Path | str], extensions: Sequence[str] = (), recursive: bool = True
) -> list[Path]:
    """Expand files and folders into a de-duplicated list of files.

    Folder contents are filtered by ``extensions`` and sorted by name; office
    lock files (``~$report.xlsx``) and hidden files are ignored.
    """
    wanted = {e.lower() for e in extensions}
    seen: set[Path] = set()
    result: list[Path] = []

    def add(path: Path) -> None:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            result.append(path)

    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            walker = path.rglob("*") if recursive else path.glob("*")
            found = [
                p
                for p in walker
                if p.is_file()
                and not p.name.startswith(("~$", "."))
                and (not wanted or p.suffix.lower() in wanted)
            ]
            for p in sorted(found, key=lambda f: str(f).casefold()):
                add(p)
        elif path.is_file() and (not wanted or path.suffix.lower() in wanted):
            add(path)
    return result


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
