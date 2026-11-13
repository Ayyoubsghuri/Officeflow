"""Desktop launcher.

Starts the local API server on a free port and shows the interface in a
frameless native window (pywebview: WebView2 on Windows). The interface draws
its own title bar; this module exposes the few things a web page cannot do on
its own — window controls, native file dialogs, full paths of files dropped
from Explorer — through pywebview's JavaScript bridge (``window.pywebview.api``).

When pywebview is not available the interface opens in the default browser.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from officeflow import APP_NAME

log = logging.getLogger("officeflow.desktop")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(app, port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           access_log=False))
    threading.Thread(target=server.run, name="officeflow-server", daemon=True).start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return server


class Bridge:
    """Methods callable from the page as ``window.pywebview.api.<name>()``."""

    def __init__(self) -> None:
        self.window = None
        self._maximized = False
        self._normal_geometry: tuple[int, int, int, int] | None = None

    # window controls ---------------------------------------------------------
    def minimize(self) -> None:
        self.window.minimize()

    def toggle_maximize(self) -> bool:
        if self._maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self._maximized = not self._maximized
        return self._maximized

    def is_maximized(self) -> bool:
        return self._maximized

    def close(self) -> None:
        self.window.destroy()

    def geometry(self) -> dict[str, int]:
        return {"x": self.window.x, "y": self.window.y, "width": self.window.width, "height": self.window.height}

    def set_geometry(self, x: int, y: int, width: int, height: int) -> None:
        """Used by the resize handles drawn by the page (frameless windows have no native border)."""
        width, height = max(int(width), 1100), max(int(height), 700)
        if (int(x), int(y)) != (self.window.x, self.window.y):
            self.window.move(int(x), int(y))
        if (width, height) != (self.window.width, self.window.height):
            self.window.resize(width, height)

    # dialogs -----------------------------------------------------------------------
    def _dialog(self, kind, **options):
        result = self.window.create_file_dialog(kind, **options)
        if not result:
            return []
        return [result] if isinstance(result, str) else list(result)

    def open_files(self, extensions: list[str] | None = None, directory: str = "") -> list[str]:
        import webview

        types = ()
        if extensions:
            pattern = ";".join(f"*{e}" for e in extensions)
            types = (f"Supported files ({pattern})", "All files (*.*)")
        return self._dialog(webview.FileDialog.OPEN, allow_multiple=True, file_types=types, directory=directory)

    def open_folder(self, directory: str = "") -> list[str]:
        import webview

        return self._dialog(webview.FileDialog.FOLDER, directory=directory)

    # shell -------------------------------------------------------------------------
    def open_path(self, path: str) -> None:
        from officeflow.server.app import open_in_explorer

        open_in_explorer(Path(path))


def _watch_drops(window) -> None:
    """Forward files dropped from Explorer, with their full paths, to the page
    as a ``officeflow-drop`` event at the drop position."""
    from webview.dom import DOMEventHandler

    def on_drop(event) -> None:
        files = event.get("dataTransfer", {}).get("files", [])
        found = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if found:
            detail = json.dumps({"paths": found, "x": event.get("clientX", 0), "y": event.get("clientY", 0)})
            window.evaluate_js(f"window.dispatchEvent(new CustomEvent('officeflow-drop', {{detail: {detail}}}))")

    def noop(_event) -> None:
        pass

    window.dom.document.events.dragover += DOMEventHandler(noop, True, True)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="officeflow", description=f"{APP_NAME} — offline office automation")
    parser.add_argument("--browser", action="store_true", help="open the interface in the default browser")
    parser.add_argument("--serve", action="store_true", help="only run the API server (development)")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default="", help="fixed API token (development)")
    args = parser.parse_args(argv)

    from officeflow.server.app import create_app

    token = args.token or os.environ.get("OFFICEFLOW_TOKEN") or secrets.token_urlsafe(24)
    dev_origins = ["http://localhost:3000", "http://127.0.0.1:3000"] if args.serve else None
    app = create_app(token, dev_origins)
    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}/?token={token}"

    if args.serve:
        print(f"OfficeFlow API on http://127.0.0.1:{port}  token={token}")
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        return 0

    server = start_server(app, port)
    webview = None
    if not args.browser:
        try:
            import webview  # noqa: F811
        except Exception as exc:  # noqa: BLE001 - missing or broken GUI backend
            log.warning("Desktop window unavailable (%s); using the browser", exc)
            webview = None

    if webview is None:
        print(f"OfficeFlow is running at {url}\nClose this window or press Ctrl+C to stop.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.should_exit = True
        return 0

    bridge = Bridge()
    window = webview.create_window(
        APP_NAME, url, js_api=bridge, width=1440, height=900, min_size=(1100, 700), frameless=True,
        easy_drag=False, background_color="#0A0B0C", text_select=False)
    bridge.window = window
    app.state.window = window
    webview.settings["DRAG_REGION_SELECTOR"] = ".drag-region"
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True

    def on_closing() -> bool:
        if app.state.jobs.busy():
            confirmed = window.create_confirmation_dialog(APP_NAME, "A task is still running. Quit anyway?")
            return bool(confirmed)
        return True

    window.events.closing += on_closing
    window.events.loaded += lambda: _watch_drops(window)
    try:
        from officeflow.services import paths

        webview.start(private_mode=False, storage_path=str(paths.app_home() / "webview"))
    finally:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
