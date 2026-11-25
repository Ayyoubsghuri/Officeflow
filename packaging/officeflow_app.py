"""Entry point of the packaged application (OfficeFlow.exe)."""

import os
import sys
import traceback

# A windowed executable has no console: give Python somewhere to write so that
# libraries which print or check the terminal (uvicorn's logging) keep working.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def report_startup_error() -> None:
    """Without a console a crash would be invisible: log it and tell the user."""
    details = traceback.format_exc()
    location = ""
    try:
        from officeflow.services import paths

        file = paths.log_file().parent / "startup-error.log"
        file.write_text(details, encoding="utf-8")
        location = f"\n\nDetails were saved to:\n{file}"
    except Exception:  # noqa: BLE001 - reporting must never fail
        pass
    if sys.platform == "win32":
        import ctypes

        message = f"OfficeFlow could not start.\n\n{details.strip().splitlines()[-1]}{location}"
        ctypes.windll.user32.MessageBoxW(None, message, "OfficeFlow", 0x10)


if __name__ == "__main__":
    try:
        from officeflow.desktop import main

        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        report_startup_error()
        sys.exit(1)
