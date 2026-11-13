"""Static safety check for plugin code written by the AI.

A plugin runs on this computer with the user's permissions, so before it can
be installed its source must pass these rules:

* it may only import an allow-list of offline libraries (no networking, no
  launching programs, no dynamic imports) — so a plugin cannot send data out;
* no eval/exec/compile/__import__, no access to dunder attributes;
* it defines at least one ``@register`` class with id, name, category,
  description and file formats, and its ids do not replace built-in tools.

This is a review aid, not a sandbox: the user still reads the code and must
approve the installation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

ALLOWED_MODULES = {
    # standard library — offline only
    "re", "json", "csv", "math", "statistics", "decimal", "fractions", "datetime", "time", "calendar",
    "pathlib", "collections", "itertools", "functools", "operator", "string", "textwrap", "unicodedata",
    "typing", "dataclasses", "enum", "io", "zipfile", "hashlib", "base64", "difflib", "shutil", "copy",
    "html", "xml", "uuid", "random", "__future__",
    # document libraries bundled with OfficeFlow
    "pandas", "openpyxl", "pymupdf", "fitz", "docx",
    # OfficeFlow itself
    "officeflow",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "breakpoint", "input"}
ALLOWED_DUNDERS = {"__name__", "__init__", "__future__"}
DELETING = {"unlink", "rmtree", "rmdir", "remove"}
CATEGORIES = {"excel", "pdf", "word", "cross"}
REQUIRED = ("id", "name", "category", "description")


@dataclass
class CheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tools: list[dict[str, str]] = field(default_factory=list)


def _root(module: str | None) -> str:
    return (module or "").split(".")[0]


def _literal(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except Exception:  # noqa: BLE001
        return None


def check_plugin(code: str, builtin_ids: set[str]) -> CheckResult:
    result = CheckResult(ok=False)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        result.errors.append(f"Syntax error on line {exc.lineno}: {exc.msg}")
        return result

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _root(alias.name) not in ALLOWED_MODULES:
                    result.errors.append(f"Line {node.lineno}: importing “{alias.name}” is not allowed.")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and _root(node.module) not in ALLOWED_MODULES:
                result.errors.append(f"Line {node.lineno}: importing from “{node.module}” is not allowed.")
            if node.level:
                result.errors.append(f"Line {node.lineno}: relative imports are not allowed.")
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else "")
            if name in FORBIDDEN_CALLS:
                result.errors.append(f"Line {node.lineno}: calling “{name}” is not allowed.")
            if name in DELETING:
                result.warnings.append(f"Line {node.lineno}: deletes files or folders (“{name}”).")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr not in ALLOWED_DUNDERS:
            result.errors.append(f"Line {node.lineno}: access to “{node.attr}” is not allowed.")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_CALLS:
            result.errors.append(f"Line {node.lineno}: using “{node.id}” is not allowed.")

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        registered = any((isinstance(d, ast.Name) and d.id == "register")
                         or (isinstance(d, ast.Attribute) and d.attr == "register") for d in node.decorator_list)
        if not registered:
            continue
        fields: dict[str, object] = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        fields[target.id] = _literal(item.value)
                    elif isinstance(target, ast.Tuple) and isinstance(item.value, ast.Tuple):
                        for t, v in zip(target.elts, item.value.elts):
                            if isinstance(t, ast.Name):
                                fields[t.id] = _literal(v)
        missing = [k for k in REQUIRED if not isinstance(fields.get(k), str) or not fields.get(k)]
        if missing:
            result.errors.append(f"Class {node.name}: missing {', '.join(missing)} (plain text values).")
            continue
        tool_id, category = str(fields["id"]), str(fields["category"])
        if category not in CATEGORIES:
            result.errors.append(f"Class {node.name}: category must be one of {', '.join(sorted(CATEGORIES))}.")
        if not tool_id.startswith(f"{category}."):
            result.errors.append(f"Class {node.name}: id “{tool_id}” must start with “{category}.”.")
        if tool_id in builtin_ids:
            result.errors.append(f"Class {node.name}: id “{tool_id}” would replace a built-in tool.")
        for key in ("input_extensions", "output_extensions"):
            value = fields.get(key)
            if not (isinstance(value, tuple) and value and all(isinstance(e, str) and e.startswith(".") for e in value)):
                result.errors.append(f"Class {node.name}: {key} must be a tuple of extensions like (\".pdf\",).")
        result.tools.append({"id": tool_id, "name": str(fields["name"]), "category": category,
                             "class": node.name})
    if not result.tools and not result.errors:
        result.errors.append("No @register tool class found.")
    result.ok = not result.errors
    return result
