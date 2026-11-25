"""Operation registry and plugin discovery.

Built-in tools live in ``officeflow.operations``; every module there is
imported at start-up and registers its operations with ``@register``. Extra
tools can be dropped as ``.py`` files into the user plugin folder — they use
exactly the same decorator, so adding a tool never requires touching the GUI.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from pathlib import Path

from officeflow.core.operation import Operation

log = logging.getLogger(__name__)

CATEGORIES: dict[str, str] = {
    "excel": "Excel",
    "pdf": "PDF",
    "word": "Word",
    "cross": "Cross-document",
}

_operations: dict[str, Operation] = {}
_plugin_tools: dict[str, list[str]] = {}     # plugin file name → ids it registered
_builtin_ids: set[str] = set()
_loading: list[str] = []                      # plugin file currently being imported


def register(cls: type[Operation]) -> type[Operation]:
    """Class decorator: instantiate and register an operation."""
    for attr in ("id", "name", "category"):
        if not getattr(cls, attr, None):
            raise TypeError(f"{cls.__name__} must define “{attr}”")
    if cls.category not in CATEGORIES:
        raise TypeError(f"{cls.__name__}: unknown category {cls.category!r}")
    if _loading:
        if cls.id in _builtin_ids:
            raise TypeError(f"{cls.__name__}: plugins cannot replace the built-in tool {cls.id!r}")
        _plugin_tools.setdefault(_loading[-1], []).append(cls.id)
    _operations[cls.id] = cls()
    return cls


def builtin_ids() -> set[str]:
    return set(_builtin_ids)


def plugin_tools() -> dict[str, list[str]]:
    return {name: list(ids) for name, ids in _plugin_tools.items()}


def get(op_id: str) -> Operation:
    try:
        return _operations[op_id]
    except KeyError:
        raise KeyError(f"Unknown operation: {op_id}") from None


def all_operations() -> list[Operation]:
    return list(_operations.values())


def by_category(category: str) -> list[Operation]:
    return [op for op in _operations.values() if op.category == category]


def load_builtin() -> None:
    import officeflow.operations as package

    names = {module.name for module in pkgutil.iter_modules(package.__path__)}
    # A packaged application may not be able to list its modules: fall back to the known ones.
    names |= {"excel", "pdf", "word"}
    for name in sorted(names):
        importlib.import_module(f"{package.__name__}.{name}")
    _builtin_ids.update(op.id for op in _operations.values() if not any(op.id in v for v in _plugin_tools.values()))


def load_plugin(path: Path) -> list[str]:
    """Import one plugin file (replacing tools it registered before) and
    return the ids it registered."""
    unload_plugin(path.name)
    spec = importlib.util.spec_from_file_location(f"officeflow_plugin_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    _loading.append(path.name)
    try:
        spec.loader.exec_module(module)
    except Exception:
        unload_plugin(path.name)
        raise
    finally:
        _loading.pop()
    return list(_plugin_tools.get(path.name, []))


def unload_plugin(name: str) -> None:
    for op_id in _plugin_tools.pop(name, []):
        if op_id not in _builtin_ids:
            _operations.pop(op_id, None)


def load_plugins(folder: Path) -> list[str]:
    """Import every ``*.py`` in ``folder``. A broken plugin is logged and
    skipped; it never prevents the application from starting."""
    problems: list[str] = []
    if not folder.is_dir():
        return problems
    for path in sorted(folder.glob("*.py")):
        try:
            load_plugin(path)
        except Exception as exc:  # noqa: BLE001 - plugins are untrusted code
            log.exception("Plugin %s failed to load", path.name)
            problems.append(f"{path.name}: {exc}")
    return problems
