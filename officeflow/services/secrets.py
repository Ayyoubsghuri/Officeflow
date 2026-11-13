"""Local storage for the AI API key.

On Windows the key is encrypted with DPAPI (only the same Windows user on the
same computer can decrypt it). Elsewhere it is stored in a file readable only
by the current user. The key is never sent to the interface, only a hint.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from officeflow.services import paths


def _file() -> Path:
    return paths.app_home() / "secrets.json"


def _protect(data: bytes) -> tuple[str, str]:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        source = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
        out = Blob()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "OfficeFlow", None, None, None, 0,
                                                      ctypes.byref(out)):
            raise OSError("Windows could not encrypt the key (CryptProtectData failed).")
        try:
            encrypted = ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
        return "dpapi", base64.b64encode(encrypted).decode()
    return "plain", base64.b64encode(data).decode()


def _unprotect(kind: str, value: str) -> bytes:
    raw = base64.b64decode(value)
    if kind == "dpapi":
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        source = Blob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_char)))
        out = Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0,
                                                        ctypes.byref(out)):
            raise OSError("Windows could not decrypt the stored key.")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
    return raw


def save_api_key(key: str) -> None:
    kind, value = _protect(key.strip().encode())
    file = _file()
    file.write_text(json.dumps({"anthropic_api_key": {"kind": kind, "value": value}}), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(file, 0o600)


def load_api_key() -> str:
    """Stored key, else the ANTHROPIC_API_KEY environment variable, else ""."""
    try:
        entry = json.loads(_file().read_text(encoding="utf-8"))["anthropic_api_key"]
        return _unprotect(entry["kind"], entry["value"]).decode()
    except (FileNotFoundError, KeyError, ValueError, OSError):
        return os.environ.get("ANTHROPIC_API_KEY", "")


def delete_api_key() -> None:
    _file().unlink(missing_ok=True)


def key_hint() -> str:
    key = load_api_key()
    return f"…{key[-4:]}" if len(key) >= 8 else ""
