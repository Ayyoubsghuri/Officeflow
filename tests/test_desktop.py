import inspect

from officeflow.desktop import Bridge


def test_bridge_exposes_only_methods_to_javascript():
    """pywebview walks every public attribute of the js_api object recursively;
    a public non-method attribute (such as the window) makes it recurse through
    the native window object on Windows."""
    bridge = Bridge()
    bridge._window = object()
    public = {name: getattr(bridge, name) for name in dir(bridge) if not name.startswith("_")}
    assert public, "the bridge must expose its API methods"
    assert all(inspect.ismethod(value) for value in public.values()), [
        name for name, value in public.items() if not inspect.ismethod(value)]


def test_webview_profile_is_per_version_and_old_ones_are_removed(tmp_path, monkeypatch):
    from officeflow import __version__
    from officeflow.desktop import webview_storage

    monkeypatch.setenv("OFFICEFLOW_HOME", str(tmp_path))
    root = tmp_path / "webview"
    for old in ("v0.2.0", "EBWebView"):
        (root / old / "Cache").mkdir(parents=True)
    (root / "notes.txt").write_text("kept")
    path = webview_storage()
    assert path == root / f"v{__version__}" and path.is_dir()
    assert sorted(p.name for p in root.iterdir()) == ["notes.txt", f"v{__version__}"]
