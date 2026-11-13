"""Reading and writing tabular files (Excel workbooks and CSV)."""

from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from typing import Mapping

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from officeflow.core.operation import OperationError
from officeflow.services.textnorm import contains_arabic

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
CSV_EXTENSIONS = (".csv", ".tsv")
TABLE_EXTENSIONS = EXCEL_EXTENSIONS + CSV_EXTENSIONS

_HEADER_FILL = PatternFill("solid", fgColor="0B1A2B")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_TOTAL_FONT = Font(bold=True)
_TOTAL_FILL = PatternFill("solid", fgColor="DFF9E7")


# -- CSV -----------------------------------------------------------------
def detect_csv_format(path: Path) -> tuple[str, str]:
    """Guess (encoding, delimiter). Handles UTF-8/UTF-16 with or without BOM
    and the legacy Windows code pages used for Arabic (1256) and French (1252)."""
    with open(path, "rb") as handle:
        raw = handle.read(256_000)
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    else:
        try:
            raw.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError as exc:
            # A multi-byte character cut by the sample boundary is still UTF-8.
            if exc.start >= len(raw) - 4:
                encoding = "utf-8-sig"
            else:
                as_arabic = raw.decode("cp1256", errors="replace")
                arabic = sum("؀" <= c <= "ۿ" for c in as_arabic)
                accented = sum(c in "éèêëàâçùûîïôœÉÈÀÇ" for c in as_arabic)
                encoding = "cp1256" if arabic > accented else "cp1252"
    sample = raw[:20_000].decode(encoding, errors="replace")
    if path.suffix.lower() == ".tsv":
        return encoding, "\t"
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample.strip() else ""
        delimiter = max(",;\t|", key=first_line.count) if first_line else ","
    return encoding, delimiter


def _read_csv(path: Path) -> pd.DataFrame:
    encoding, delimiter = detect_csv_format(path)
    # Everything is read as text so codes such as "00123" keep their zeros.
    return pd.read_csv(
        path, sep=delimiter, encoding=encoding, encoding_errors="replace", dtype=str,
        keep_default_na=False, na_values=[""], engine="python" if delimiter == "|" else "c",
    )


# -- reading -------------------------------------------------------------
def _open_error(path: Path, exc: Exception) -> OperationError:
    if path.suffix.lower() == ".xls":
        return OperationError(f"{path.name}: the old .xls format is not supported — save it as .xlsx.")
    if isinstance(exc, (zipfile.BadZipFile, KeyError)):
        return OperationError(f"{path.name}: cannot be opened (password-protected or damaged).")
    return OperationError(f"{path.name}: cannot be read ({exc}).")


def sheet_names(path: Path) -> list[str]:
    try:
        with pd.ExcelFile(path, engine="openpyxl") as book:
            return [str(n) for n in book.sheet_names]
    except Exception as exc:  # noqa: BLE001
        raise _open_error(path, exc) from None


def _read_sheets(path: Path, sheet: str | None):
    # dtype=object stops pandas from re-interpreting text cells, so a code
    # stored as the text "007" stays "007"; real numbers keep their type.
    data = pd.read_excel(path, sheet_name=sheet, engine="openpyxl", dtype=object)
    if isinstance(data, dict):
        return {name: frame.infer_objects() for name, frame in data.items()}
    return data.infer_objects()


def _tidy(frame: pd.DataFrame) -> pd.DataFrame:
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def read_table(path: Path, sheet: str = "") -> pd.DataFrame:
    """Read one table. ``sheet`` is a sheet name or 1-based number; blank
    means the first sheet. Ignored for CSV files."""
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix in CSV_EXTENSIONS:
            return _tidy(_read_csv(path))
        if suffix not in EXCEL_EXTENSIONS:
            raise OperationError(f"{path.name}: unsupported file type “{suffix}”.")
        names = sheet_names(path)
        target: str = names[0]
        if sheet:
            if sheet in names:
                target = sheet
            elif sheet.isdigit() and 1 <= int(sheet) <= len(names):
                target = names[int(sheet) - 1]
            else:
                raise OperationError(
                    f"{path.name}: no sheet “{sheet}”. Available: {', '.join(names)}."
                )
        return _tidy(_read_sheets(path, target))
    except OperationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _open_error(path, exc) from None


def read_all_sheets(path: Path) -> dict[str, pd.DataFrame]:
    path = Path(path)
    if path.suffix.lower() in CSV_EXTENSIONS:
        return {path.stem: read_table(path)}
    try:
        frames = _read_sheets(path, None)
    except Exception as exc:  # noqa: BLE001
        raise _open_error(path, exc) from None
    return {str(name): _tidy(frame) for name, frame in frames.items()}


# -- writing -------------------------------------------------------------
def sheet_title(name: object, taken: set[str] | None = None) -> str:
    """A valid, unique Excel sheet name (max 31 chars, no ``[]:*?/\\``)."""
    title = re.sub(r"[\[\]:*?/\\]", "-", str(name)).strip("' ")[:31] or "Sheet"
    if taken is not None:
        base, counter = title, 2
        while title.casefold() in taken:
            suffix = f" ({counter})"
            title = base[: 31 - len(suffix)] + suffix
            counter += 1
        taken.add(title.casefold())
    return title


def style_sheet(sheet: Worksheet, totals_row: bool = False) -> None:
    """Readable defaults: bold header, frozen first row, filters, fitted
    columns, and right-to-left layout when the headers are Arabic."""
    if sheet.max_row < 1 or sheet.max_column < 1:
        return
    headers = [str(c.value or "") for c in sheet[1]]
    for cell in sheet[1]:
        cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    last_data_row = sheet.max_row - (1 if totals_row else 0)
    if last_data_row >= 1:
        sheet.auto_filter.ref = f"A1:{get_column_letter(sheet.max_column)}{last_data_row}"
    sample = list(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 300), values_only=True))
    for index in range(sheet.max_column):
        longest = max((len(str(row[index])) for row in sample if row[index] is not None), default=6)
        sheet.column_dimensions[get_column_letter(index + 1)].width = min(max(longest + 3, 9), 60)
    if totals_row and sheet.max_row > 1:
        for cell in sheet[sheet.max_row]:
            cell.font, cell.fill = _TOTAL_FONT, _TOTAL_FILL
    arabic = sum(contains_arabic(h) for h in headers)
    if arabic and arabic >= len([h for h in headers if h]) / 2:
        sheet.sheet_view.rightToLeft = True


def write_workbook(
    path: Path, sheets: Mapping[str, pd.DataFrame], totals_on: frozenset[str] = frozenset()
) -> Path:
    """Write one or more sheets with standard formatting."""
    taken: set[str] = set()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            title = sheet_title(name, taken)
            frame.to_excel(writer, sheet_name=title, index=False)
            style_sheet(writer.sheets[title], totals_row=name in totals_on)
    return path


def write_table(frame: pd.DataFrame, path: Path, sheet: str = "Data") -> Path:
    return write_workbook(path, {sheet: frame})


def write_csv(frame: pd.DataFrame, path: Path, delimiter: str = ",") -> Path:
    # utf-8-sig so Excel opens Arabic and accented text correctly.
    frame.to_csv(path, index=False, sep=delimiter, encoding="utf-8-sig")
    return path
