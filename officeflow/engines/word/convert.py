"""Word → PDF conversion through an office suite installed on the computer.

LibreOffice (free) is used when it is found. On Windows, Microsoft Word is
used as a fallback through PowerShell automation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from officeflow.core.operation import OperationError

TIMEOUT = 240


def find_libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")):
            candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
            if candidate.exists():
                return str(candidate)
    if sys.platform == "darwin":
        candidate = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if candidate.exists():
            return str(candidate)
    return None


def _libreoffice(soffice: str, source: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="officeflow-") as work:
        profile = Path(work, "profile").as_uri()  # private profile: works while LibreOffice is open
        result = subprocess.run(
            [soffice, f"-env:UserInstallation={profile}", "--headless", "--norestore",
             "--convert-to", "pdf", "--outdir", work, str(source)],
            capture_output=True, text=True, timeout=TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        produced = Path(work) / (source.stem + ".pdf")
        if not produced.exists():
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise OperationError(f"{source.name}: conversion failed ({detail[-1] if detail else 'no output'}).")
        shutil.move(str(produced), destination)


def _word(source: Path, destination: Path) -> None:
    script = (
        "$ErrorActionPreference='Stop';"
        "$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
        "try{$d=$w.Documents.Open($env:OF_SRC,$false,$true);$d.SaveAs([ref]$env:OF_DST,[ref]17);$d.Close($false)}"
        "finally{$w.Quit()}"
    )
    env = {**os.environ, "OF_SRC": str(source.resolve()), "OF_DST": str(destination.resolve())}
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, timeout=TIMEOUT, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0 or not destination.exists():
        raise OperationError(f"{source.name}: Microsoft Word could not convert it ({result.stderr.strip()[:200]}).")


def converter_name() -> str | None:
    if find_libreoffice():
        return "LibreOffice"
    if sys.platform == "win32" and shutil.which("powershell"):
        return "Microsoft Word"
    return None


def to_pdf(source: Path, destination: Path) -> None:
    soffice = find_libreoffice()
    try:
        if soffice:
            _libreoffice(soffice, source, destination)
        elif sys.platform == "win32" and shutil.which("powershell"):
            _word(source, destination)
        else:
            raise OperationError("Converting to PDF needs LibreOffice (free, libreoffice.org) or Microsoft Word "
                                 "installed on this computer.")
    except subprocess.TimeoutExpired:
        raise OperationError(f"{source.name}: conversion took longer than {TIMEOUT} seconds.") from None
