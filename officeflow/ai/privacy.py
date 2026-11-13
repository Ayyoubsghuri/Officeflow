"""What may leave the computer, and the filter applied to it.

Only two things are ever sent to the AI provider:

1. the tool catalog — names, descriptions, settings and file formats of
   OfficeFlow's tools (product information, no user data);
2. the user's request text, after file paths and e-mail addresses have been
   replaced by placeholders. The user sees this exact text before sending.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from officeflow.core import registry

_PATTERNS = [
    # C:\… and \\server\… — folder names may contain spaces; the last part may not
    ("path", re.compile(r"(?:[A-Za-z]:\\|\\\\)(?:[^\\\s\"'<>|?*:,;][^\\\n\"'<>|?*:,;]*\\)*[^\\\s\"'<>|?*,;]*")),
    ("path", re.compile(r"(?<![\w/])(?:~|/(?:home|Users|mnt|media|tmp|var|srv|opt|data))/[^\s\"'<>]+")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
]


@dataclass
class Redaction:
    text: str
    replaced: list[dict[str, str]] = field(default_factory=list)


def redact(text: str) -> Redaction:
    """Replace file paths and e-mail addresses with numbered placeholders."""
    replaced: list[dict[str, str]] = []
    counters: dict[str, int] = {}
    seen: dict[str, str] = {}

    def substitute(kind: str):
        def inner(match: re.Match[str]) -> str:
            original = match.group(0).rstrip(".,;:)")
            tail = match.group(0)[len(original):]
            if original not in seen:
                counters[kind] = counters.get(kind, 0) + 1
                seen[original] = f"<{kind}-{counters[kind]}>"
                replaced.append({"kind": kind, "original": original, "placeholder": seen[original]})
            return seen[original] + tail
        return inner

    for kind, pattern in _PATTERNS:
        text = pattern.sub(substitute(kind), text)
    return Redaction(text, replaced)


def catalog() -> list[dict[str, Any]]:
    """The tool catalog sent to the AI: product information only."""
    tools = []
    for op in sorted(registry.all_operations(), key=lambda o: o.id):
        tools.append({
            "id": op.id, "name": op.name, "category": op.category, "description": op.description,
            "reads": list(op.input_extensions), "writes": list(op.output_extensions),
            "min_inputs": op.min_inputs, "max_inputs": op.max_inputs,
            "params": [{"key": p.key, "label": p.label, "type": p.type.value, "default": p.default,
                        "required": p.required, "help": p.help,
                        **({"choices": [c[0] for c in p.choices]} if p.choices else {}),
                        **({"min": p.minimum, "max": p.maximum} if p.type.value == "int" else {})}
                       for p in op.params],
        })
    return tools
