"""Fill a Word template from table rows ("mail merge").

Placeholders are written ``{{Column name}}`` in the template — in the body,
tables, headers and footers. Column names are matched forgivingly (case,
spaces, accents, Arabic letter variants), so ``{{nom client}}`` finds the
column "Nom Client".
"""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from officeflow.engines.word.document import iter_paragraphs, open_docx, replace_in_document
from officeflow.services.textnorm import header_key

PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def format_value(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return ""
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return value.strftime("%d/%m/%Y") if (value.hour, value.minute) == (0, 0) else value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def template_fields(template: Path) -> list[str]:
    document = open_docx(template)
    found: dict[str, None] = {}
    for paragraph in iter_paragraphs(document):
        for match in PLACEHOLDER.finditer(paragraph.text):
            found.setdefault(match.group(1))
    return list(found)


def column_map(fields: list[str], columns: list[str]) -> tuple[dict[str, str], list[str]]:
    """field → column, plus the fields that match no column."""
    by_key = {header_key(c): c for c in columns}
    mapping, missing = {}, []
    for field in fields:
        if field in columns:
            mapping[field] = field
        elif header_key(field) in by_key:
            mapping[field] = by_key[header_key(field)]
        elif field.lower() != "n":
            missing.append(field)
    return mapping, missing


def fill(template: Path, row: dict[str, Any], mapping: dict[str, str], number: int, destination: Path) -> int:
    document = open_docx(template)

    def value(match: re.Match[str]) -> str:
        field = match.group(1)
        if field in mapping:
            return format_value(row.get(mapping[field]))
        if field.lower() == "n":
            return str(number)
        return match.group(0)  # unknown placeholder stays visible

    count = replace_in_document(document, PLACEHOLDER, value)
    document.save(str(destination))
    return count


def file_name(template: str, row: dict[str, Any], mapping: dict[str, str], columns: list[str], number: int) -> str:
    extra, _ = column_map([m.group(1) for m in PLACEHOLDER.finditer(template)], columns)
    mapping = {**extra, **mapping}

    def value(match: re.Match[str]) -> str:
        field = match.group(1)
        if field.lower() == "n":
            return f"{number:03d}"
        return format_value(row.get(mapping[field])) if field in mapping else field

    return PLACEHOLDER.sub(value, template)
