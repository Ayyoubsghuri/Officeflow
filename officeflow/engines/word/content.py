"""Reading content out of Word documents and normalising their layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from officeflow.engines.word.document import iter_paragraphs, open_docx
from officeflow.services.textnorm import contains_arabic


def extract_tables(source: Path) -> list[pd.DataFrame]:
    document = open_docx(source)
    tables = []
    for table in document.tables:
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() or None for cell in row.cells])
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        width = max(len(r) for r in rows)
        rows = [r + [None] * (width - len(r)) for r in rows]
        header = rows[0]
        if len(rows) > 1 and all(header) and len(set(header)) == len(header):
            tables.append(pd.DataFrame(rows[1:], columns=header))
        else:
            tables.append(pd.DataFrame(rows, columns=[f"Column {i + 1}" for i in range(width)]))
    return tables


def export_text(source: Path, destination: Path) -> int:
    document = open_docx(source)
    lines = [p.text for p in iter_paragraphs(document, headers=False)]
    text = "\n".join(lines).strip() + "\n"
    destination.write_text(text, encoding="utf-8")
    return len(text.strip())


@dataclass
class FormatOptions:
    font: str = "Calibri"
    arabic_font: str = "Arial"
    size: float = 11
    line_spacing: float = 1.15
    margin_cm: float = 2.0
    justify: bool = False
    remove_empty: bool = True
    rtl_arabic: bool = True


def _set_fonts(rpr_owner, options: FormatOptions) -> None:
    font = rpr_owner.font
    font.name = options.font
    font.size = Pt(options.size)
    element = rpr_owner._r if hasattr(rpr_owner, "_r") else rpr_owner.element
    rpr = element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        fonts.set(qn(attr), options.font)
    fonts.set(qn("w:cs"), options.arabic_font)  # complex scripts (Arabic)
    size = rpr.find(qn("w:szCs"))
    if size is None:
        size = rpr.makeelement(qn("w:szCs"), {})
        rpr.append(size)
    size.set(qn("w:val"), str(int(options.size * 2)))


def _set_rtl(paragraph) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    if ppr.find(qn("w:bidi")) is None:
        ppr.append(ppr.makeelement(qn("w:bidi"), {}))
    for run in paragraph.runs:
        rpr = run._r.get_or_add_rPr()
        if rpr.find(qn("w:rtl")) is None:
            rpr.append(rpr.makeelement(qn("w:rtl"), {}))


def format_document(source: Path, destination: Path, options: FormatOptions) -> dict[str, int]:
    document = open_docx(source)
    stats = {"paragraphs": 0, "removed": 0, "rtl": 0}
    normal = document.styles["Normal"]
    _set_fonts(normal, options)
    normal.paragraph_format.line_spacing = options.line_spacing
    for section in document.sections:
        section.left_margin = section.right_margin = Cm(options.margin_cm)
        section.top_margin = section.bottom_margin = Cm(options.margin_cm)
    for paragraph in list(iter_paragraphs(document, headers=False)):
        has_content = paragraph.text.strip() or paragraph._p.xpath(".//w:drawing|.//w:pict|.//w:br[@w:type='page']")
        if options.remove_empty and not has_content and paragraph._p.getparent().tag == qn("w:body"):
            paragraph._p.getparent().remove(paragraph._p)
            stats["removed"] += 1
            continue
        stats["paragraphs"] += 1
        for run in paragraph.runs:
            _set_fonts(run, options)
        style_name = (paragraph.style.name if paragraph.style is not None else "").lower()
        is_heading = style_name.startswith(("heading", "title", "titre"))
        if not is_heading:
            paragraph.paragraph_format.line_spacing = options.line_spacing
        arabic = options.rtl_arabic and contains_arabic(paragraph.text)
        if arabic:
            _set_rtl(paragraph)
            stats["rtl"] += 1
        if options.justify and not is_heading and len(paragraph.text) > 80:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        elif arabic and paragraph.alignment in (None, WD_ALIGN_PARAGRAPH.LEFT):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    document.save(str(destination))
    return stats
