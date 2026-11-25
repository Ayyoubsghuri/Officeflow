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


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d") if getattr(value, "hour", 0) == 0 and getattr(value, "minute", 0) == 0 \
            else value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _shade(cell, color: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = tcpr.makeelement(qn("w:shd"), {qn("w:val"): "clear", qn("w:color"): "auto", qn("w:fill"): color})
    tcpr.append(shd)


def tables_to_docx(tables: list[tuple[str, pd.DataFrame]], destination: Path, headings: bool = True,
                   landscape: str = "auto") -> int:
    """Write tables into a new Word document, no template needed: one titled,
    bordered table per entry, header row bold and shaded, right-to-left when the
    table contains Arabic, landscape pages for wide tables (``landscape``:
    "auto", "yes" or "no"). Returns the number of tables written."""
    import docx
    from docx.enum.section import WD_ORIENT

    document = docx.Document()
    section = document.sections[0]
    widest = max((len(frame.columns) for _, frame in tables), default=0)
    if landscape == "yes" or (landscape == "auto" and widest > 6):
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
    for margin in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, margin, Cm(1.8))
    small = Pt(9) if widest > 8 else Pt(10)

    for index, (title, frame) in enumerate(tables):
        header = [str(c) for c in frame.columns]
        body = [[_cell_text(v) for v in row] for row in frame.itertuples(index=False)]
        arabic = contains_arabic(" ".join(header + [c for row in body for c in row]))
        if headings and title:
            heading = document.add_heading(title, level=2)
            if arabic:
                heading.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _set_rtl(heading)
        table = document.add_table(rows=1 + len(body), cols=max(len(header), 1))
        table.style = "Table Grid"
        if arabic:
            tblpr = table._tbl.tblPr
            tblpr.append(tblpr.makeelement(qn("w:bidiVisual"), {}))
        for r, values in enumerate([header] + body):
            for c, text in enumerate(values):
                cell = table.rows[r].cells[c]
                paragraph = cell.paragraphs[0]
                run = paragraph.add_run(text)
                run.font.size = small
                if r == 0:
                    run.bold = True
                    _shade(cell, "DFF9E7")
                if arabic:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _set_rtl(paragraph)
        # the first row repeats at the top of every page the table runs over
        trpr = table.rows[0]._tr.get_or_add_trPr()
        trpr.append(trpr.makeelement(qn("w:tblHeader"), {}))
        if index < len(tables) - 1:
            document.add_paragraph()
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(destination))
    return len(tables)
