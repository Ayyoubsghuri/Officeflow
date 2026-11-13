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
