"""Page-level PDF operations: merge, split, extract pages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import pymupdf

from officeflow.core.operation import OperationError
from officeflow.engines.pdf.reader import PdfError, open_pdf


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """``"1-3, 5, 10-"`` → zero-based page indexes ``[0, 1, 2, 4, 9, …]``.
    Arabic digits and the Arabic comma are accepted."""
    from officeflow.services.textnorm import to_western_digits

    pages: list[int] = []
    for part in re.split(r"[,،;\s]+", to_western_digits(spec).strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d*)\s*(-?)\s*(\d*)", part)
        if not match or not (match.group(1) or match.group(3)):
            raise OperationError(f"Invalid page range “{part}”. Example: 1-3, 5, 10-")
        start = int(match.group(1) or 1)
        end = int(match.group(3)) if match.group(3) else (page_count if match.group(2) else start)
        if start < 1 or (match.group(3) and end < start):
            raise OperationError(f"Invalid page range “{part}”.")
        pages.extend(range(start - 1, min(end, page_count)))
    return pages


def merge_pdfs(sources: Sequence[Path], destination: Path, progress=None) -> tuple[int, list[str]]:
    """Merge PDFs in order, adding one bookmark per source file. Unreadable
    files are skipped and reported. Returns (page count, errors)."""
    errors: list[str] = []
    toc: list[list[object]] = []
    with pymupdf.open() as merged:
        for index, source in enumerate(sources):
            if progress:
                progress(index, len(sources), source.name)
            try:
                with open_pdf(source) as document:
                    start = merged.page_count
                    merged.insert_pdf(document)
                    toc.append([1, source.stem, start + 1])
            except PdfError as exc:
                errors.append(str(exc))
        if merged.page_count == 0:
            raise OperationError("None of the PDFs could be read. " + " ".join(errors))
        merged.set_toc(toc)
        pages = merged.page_count
        merged.save(destination, garbage=3, deflate=True)
    return pages, errors


def _save_pages(document: pymupdf.Document, pages: Sequence[int], destination: Path) -> None:
    with pymupdf.open() as part:
        if pages and list(pages) == list(range(pages[0], pages[-1] + 1)):
            part.insert_pdf(document, from_page=pages[0], to_page=pages[-1])
        else:
            for page in pages:
                part.insert_pdf(document, from_page=page, to_page=page)
        part.save(destination, garbage=3, deflate=True)


def split_pdf(source: Path, pages_per_file: int, make_path) -> list[Path]:
    """Split into chunks of ``pages_per_file`` pages. ``make_path(name)``
    supplies a non-overwriting destination for each part."""
    outputs: list[Path] = []
    with open_pdf(source) as document:
        total = document.page_count
        width = len(str(total))
        for start in range(0, total, pages_per_file):
            end = min(start + pages_per_file, total)
            label = f"{start + 1:0{width}d}" if end - start == 1 else f"{start + 1:0{width}d}-{end:0{width}d}"
            destination = make_path(f"{source.stem} - p{label}.pdf")
            _save_pages(document, range(start, end), destination)
            outputs.append(destination)
    return outputs


def extract_pages(source: Path, spec: str, destination: Path) -> int:
    with open_pdf(source) as document:
        pages = parse_page_ranges(spec, document.page_count)
        if not pages:
            raise OperationError(
                f"{source.name}: has {document.page_count} page(s); none match “{spec}”.")
        _save_pages(document, pages, destination)
    return len(pages)
