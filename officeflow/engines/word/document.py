"""Opening Word documents, walking their text, and replacing text without
losing formatting."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Callable, Iterator

import docx
from docx.document import Document
from docx.table import Table
from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from officeflow.core.operation import OperationError

WORD_EXTENSIONS = (".docx",)


def open_docx(path: Path) -> Document:
    path = Path(path)
    if path.suffix.lower() == ".doc":
        raise OperationError(f"{path.name}: the old .doc format is not supported — save it as .docx.")
    try:
        return docx.Document(str(path))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise OperationError(f"{path.name}: cannot be opened (password-protected or damaged).") from None
    except Exception as exc:  # noqa: BLE001 - python-docx raises many types
        raise OperationError(f"{path.name}: cannot be read ({exc}).") from None


def _table_paragraphs(table: Table) -> Iterator[Paragraph]:
    seen: set[int] = set()
    for row in table.rows:
        for cell in row.cells:
            if id(cell._tc) in seen:  # merged cells are returned once per spanned column
                continue
            seen.add(id(cell._tc))
            yield from cell.paragraphs
            for inner in cell.tables:
                yield from _table_paragraphs(inner)


def _story_paragraphs(story) -> Iterator[Paragraph]:
    for block in story.iter_inner_content():
        if isinstance(block, Paragraph):
            yield block
        else:
            yield from _table_paragraphs(block)


def iter_paragraphs(document: Document, headers: bool = True) -> Iterator[Paragraph]:
    """Every paragraph: body, tables (nested too), headers and footers."""
    yield from _story_paragraphs(document)
    if not headers:
        return
    seen: set[int] = set()
    for section in document.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer,
                     section.even_page_header, section.even_page_footer):
            if part.is_linked_to_previous or id(part._element) in seen:
                continue
            seen.add(id(part._element))
            yield from _story_paragraphs(part)


def paragraph_runs(paragraph: Paragraph) -> list[Run]:
    runs: list[Run] = []
    for item in paragraph.iter_inner_content():
        if isinstance(item, Hyperlink):
            runs.extend(item.runs)
        else:
            runs.append(item)
    return runs


def replace_in_paragraph(paragraph: Paragraph, pattern: re.Pattern[str],
                         replacement: Callable[[re.Match[str]], str]) -> int:
    """Replace matches even when Word split the text over several runs (which
    happens after spell-checking or partial formatting). The replacement takes
    the formatting of the run where the match starts."""
    runs = paragraph_runs(paragraph)
    texts = [run.text for run in runs]
    full = "".join(texts)
    matches = [m for m in pattern.finditer(full) if m.end() > m.start()]
    if not matches:
        return 0
    starts, offset = [], 0
    for text in texts:
        starts.append(offset)
        offset += len(text)
    texts_len = [len(t) for t in texts]
    for match in reversed(matches):
        start, end = match.span()
        first = next(i for i in range(len(runs)) if starts[i] <= start < starts[i] + texts_len[i])
        last = next(i for i in range(len(runs)) if starts[i] < end <= starts[i] + texts_len[i])
        new = replacement(match)
        if first == last:
            text = texts[first]
            texts[first] = text[: start - starts[first]] + new + text[end - starts[first]:]
        else:
            texts[first] = texts[first][: start - starts[first]] + new
            for i in range(first + 1, last):
                texts[i] = ""
            texts[last] = texts[last][end - starts[last]:]
    for run, new in zip(runs, texts):
        if run.text != new:
            run.text = new
    return len(matches)


def replace_in_document(document: Document, pattern: re.Pattern[str],
                        replacement: Callable[[re.Match[str]], str]) -> int:
    return sum(replace_in_paragraph(p, pattern, replacement) for p in iter_paragraphs(document))


def document_text(document: Document) -> str:
    return "\n".join(p.text for p in iter_paragraphs(document, headers=False))
