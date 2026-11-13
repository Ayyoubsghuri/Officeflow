"""``python -m officeflow`` / the ``officeflow`` command."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from officeflow.app import run
    except ImportError as exc:
        print(f"OfficeFlow cannot start: {exc}\nInstall the requirements: pip install -r requirements.txt",
              file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
