"""Content-level PDF operations: text export, search, tables, comparison."""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from officeflow.engines.pdf.reader import iter_page_texts, open_pdf
from officeflow.services.textnorm import contains_arabic, fix_reversed_digit_runs, normalize_text


def export_text(source: Path, destination: Path, page_markers: bool = True) -> tuple[int, int]:
    """Write the document text as UTF-8. Returns (pages, characters)."""
    pages = characters = 0
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        for number, text in enumerate(iter_page_texts(source), 1):
            text = normalize_text(text, western_digits=False).strip()
            if page_markers:
                handle.write(f"\n===== Page {number} =====\n")
            handle.write(text + "\n")
            pages, characters = number, characters + len(text)
    return pages, characters


@dataclass
class Hit:
    page: int
    match: str
    context: str


def search_pdf(source: Path, pattern: re.Pattern[str], western_digits: bool = True) -> list[Hit]:
    hits: list[Hit] = []
    for number, text in enumerate(iter_page_texts(source), 1):
        text = normalize_text(text, western_digits)
        for match in pattern.finditer(text):
            start, end = max(match.start() - 50, 0), min(match.end() + 50, len(text))
            context = re.sub(r"\s+", " ", text[start:end]).strip()
            hits.append(Hit(number, match.group(0), context))
    return hits


def _clean_cell(value: object) -> object:
    if value is None:
        return None
    text = normalize_text(fix_reversed_digit_runs(str(value)), western_digits=False)
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip() or None


def extract_tables(source: Path) -> list[tuple[int, pd.DataFrame]]:
    """Detect tables on every page. Returns (page number, table) pairs; the
    first row of each table is used as its header when it looks like one."""
    tables: list[tuple[int, pd.DataFrame]] = []
    with open_pdf(source) as document:
        for number, page in enumerate(document, 1):
            try:
                found = page.find_tables().tables
            except Exception:  # noqa: BLE001 - detection is best-effort per page
                continue
            for table in found:
                rows = [[_clean_cell(c) for c in row] for row in table.extract()]
                rows = [r for r in rows if any(c is not None for c in r)]
                if len(rows) < 2:
                    continue
                used = [i for i in range(len(rows[0])) if any(r[i] is not None for r in rows)]
                rows = [[r[i] for i in used] for r in rows]
                if len(used) < 2:
                    continue
                header = rows[0]
                if all(header) and len(set(header)) == len(header):
                    frame = pd.DataFrame(rows[1:], columns=[str(h) for h in header])
                else:
                    frame = pd.DataFrame(rows, columns=[f"Column {i + 1}" for i in range(len(header))])
                tables.append((number, frame))
    return tables


_REPORT = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body{{font-family:Segoe UI,Tahoma,Arial,sans-serif;margin:24px;color:#000b1a}}
table.diff{{border-collapse:collapse;width:100%;font-size:13px}}
td{{padding:2px 6px;vertical-align:top;white-space:pre-wrap;word-break:break-word}}
.diff_header{{background:#eef0f3;color:#667;text-align:right;width:1%}}
.diff_next{{display:none}} .diff_add{{background:#c9f7d6}} .diff_chg{{background:#fff3b0}}
.diff_sub{{background:#ffc9ca}} th{{background:#000b1a;color:#fff;padding:6px}}
</style></head><body{direction}><h2>{title}</h2><p>{summary}</p>{table}</body></html>"""


def compare_pdfs(first: Path, second: Path, destination: Path) -> dict[str, float]:
    """Compare the text of two PDFs and write a side-by-side HTML report."""

    def lines(path: Path) -> list[str]:
        result: list[str] = []
        for number, text in enumerate(iter_page_texts(path), 1):
            result.append(f"[Page {number}]")
            result += [l.rstrip() for l in normalize_text(text, False).splitlines() if l.strip()]
        return result

    a, b = lines(first), lines(second)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal")
    similarity = round(matcher.ratio() * 100, 1)
    if changed:
        table = difflib.HtmlDiff(wrapcolumn=70).make_table(
            a, b, html.escape(first.name), html.escape(second.name), context=True, numlines=2)
    else:
        table = "<p><b>The text of the two documents is identical.</b></p>"
    summary = f"Similarity: {similarity}% · {changed} differing line(s)"
    direction = ' dir="rtl"' if contains_arabic(" ".join(a[:200])) else ""
    destination.write_text(
        _REPORT.format(title=html.escape(f"{first.name} ↔ {second.name}"), summary=summary,
                       table=table, direction=direction), encoding="utf-8")
    return {"similarity": similarity, "changed_lines": changed}
