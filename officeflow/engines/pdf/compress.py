"""Make PDFs smaller: rebuild the file structure and, if asked, re-encode large images."""

from __future__ import annotations

import shutil
from pathlib import Path

from officeflow.engines.pdf.reader import PdfError, open_pdf

# level -> (images above this many dpi are reduced, to this dpi, JPEG quality); None keeps images as they are
LEVELS: dict[str, tuple[int, int, int] | None] = {
    "lossless": None,
    "balanced": (200, 150, 75),
    "strong": (120, 96, 55),
}


def compress_pdf(source: Path, destination: Path, level: str = "balanced") -> tuple[int, int]:
    """Write a smaller copy of ``source`` to ``destination``; the original is
    never changed. If the result would not be smaller, the original bytes are
    copied instead. Returns (size before, size after) in bytes."""
    before = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    images = LEVELS.get(level)
    try:
        with open_pdf(source) as document:
            if images and hasattr(document, "rewrite_images"):
                threshold, target, quality = images
                try:
                    document.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality,
                                            lossy=True, lossless=True, bitonal=False)
                except Exception:  # noqa: BLE001 - keep going with structural compression only
                    pass
            document.save(str(destination), garbage=4, clean=True, deflate=True, deflate_images=True,
                          deflate_fonts=True, use_objstms=1)
    except PdfError:
        raise
    except Exception as exc:  # noqa: BLE001 - MuPDF raises several unrelated types
        destination.unlink(missing_ok=True)
        raise PdfError(f"{source.name}: could not be compressed ({exc}).") from None
    after = destination.stat().st_size
    if after >= before:
        shutil.copyfile(source, destination)
        after = before
    return before, after


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
