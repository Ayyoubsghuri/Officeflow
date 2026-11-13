"""Opening PDFs safely and extracting normalised text."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pymupdf

from officeflow.core.operation import OperationError
from officeflow.services.textnorm import fix_reversed_digit_runs

pymupdf.TOOLS.mupdf_display_errors(False)  # problems are reported through our own errors
pymupdf.TOOLS.mupdf_display_warnings(False)

PDF_EXTENSIONS = (".pdf",)


class PdfError(OperationError):
    """A PDF that cannot be processed (damaged, encrypted, not a PDF)."""


def open_pdf(path: Path) -> pymupdf.Document:
    """Open a PDF or raise a ``PdfError`` with a message a user understands."""
    try:
        document = pymupdf.open(path)
    except Exception:  # noqa: BLE001 - MuPDF raises several unrelated types
        raise PdfError(f"{Path(path).name}: damaged file or not a PDF.") from None
    if not document.is_pdf:
        document.close()
        raise PdfError(f"{Path(path).name}: not a PDF file.")
    if document.needs_pass and not document.authenticate(""):
        document.close()
        raise PdfError(f"{Path(path).name}: password-protected.")
    return document


def page_text(page: pymupdf.Page) -> str:
    """Text of one page in reading order, with Arabic digit runs restored."""
    return fix_reversed_digit_runs(page.get_text("text"))


def iter_page_texts(path: Path, max_pages: int = 0) -> Iterator[str]:
    """Yield the text of each page (the first ``max_pages`` only, if > 0).
    Pages are read one at a time so large files do not fill the memory."""
    with open_pdf(path) as document:
        for number, page in enumerate(document):
            if max_pages and number >= max_pages:
                break
            try:
                yield page_text(page)
            except Exception:  # noqa: BLE001 - one bad page must not lose the others
                yield ""


def page_count(path: Path) -> int:
    with open_pdf(path) as document:
        return document.page_count
