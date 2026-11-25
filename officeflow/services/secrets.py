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


_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
        "nvidia": "NVIDIA_API_KEY"}


def _entries() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(entries: dict) -> None:
    file = _file()
    if not entries:
        file.unlink(missing_ok=True)
        return
    file.write_text(json.dumps(entries), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(file, 0o600)


def save_api_key(key: str, provider: str = "anthropic") -> None:
    kind, value = _protect(key.strip().encode())
    entries = _entries()
    entries[f"{provider}_api_key"] = {"kind": kind, "value": value}
    _write(entries)


def load_api_key(provider: str = "anthropic") -> str:
    """Stored key for the provider, else its environment variable, else ""."""
    entry = _entries().get(f"{provider}_api_key")
    if entry:
        try:
            return _unprotect(entry["kind"], entry["value"]).decode()
        except (KeyError, ValueError, OSError):
            pass
    return os.environ.get(_ENV.get(provider, ""), "")


def delete_api_key(provider: str = "anthropic") -> None:
    entries = _entries()
    entries.pop(f"{provider}_api_key", None)
    _write(entries)


def key_hint(provider: str = "anthropic") -> str:
    key = load_api_key(provider)
    return f"…{key[-4:]}" if len(key) >= 8 else ""
