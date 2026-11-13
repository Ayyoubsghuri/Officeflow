"""Search and replace inside workbooks while preserving their formatting."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import openpyxl

from officeflow.engines.excel import io


def _apply(pattern: re.Pattern[str], replacement: str, regex: bool, whole_cell: bool,
           text: str) -> tuple[str, int]:
    if whole_cell:
        if not pattern.fullmatch(text):
            return text, 0
        return (pattern.sub(replacement, text) if regex else replacement), 1
    if regex:
        return pattern.subn(replacement, text)
    return pattern.subn(lambda _m: replacement, text)


def replace_in_file(
    source: Path, destination: Path | None, pattern: re.Pattern[str], replacement: str,
    regex: bool = False, whole_cell: bool = False,
) -> int:
    """Replace text cells (formulas and numbers are left untouched) and save
    the result to ``destination``. With ``destination=None`` nothing is
    written: the function only counts matches (used for previews)."""
    count = 0
    if source.suffix.lower() in io.CSV_EXTENSIONS:
        frame = io.read_table(source)

        def fix(value: object) -> object:
            nonlocal count
            if not isinstance(value, str):
                return value
            new, hits = _apply(pattern, replacement, regex, whole_cell, value)
            count += hits
            return new

        frame = frame.apply(lambda column: column.map(fix))
        if destination is not None:
            _, delimiter = io.detect_csv_format(source)
            io.write_csv(frame, destination, delimiter)
        return count
    try:
        book = openpyxl.load_workbook(source, keep_vba=source.suffix.lower() == ".xlsm")
    except Exception as exc:  # noqa: BLE001
        raise io._open_error(source, exc) from None
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == "s" and isinstance(cell.value, str):
                    new, hits = _apply(pattern, replacement, regex, whole_cell, cell.value)
                    if hits:
                        count += hits
                        cell.value = new
    if destination is not None:
        if count:
            book.save(destination)
        else:
            shutil.copy2(source, destination)
    book.close()
    return count
