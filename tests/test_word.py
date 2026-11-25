from pathlib import Path

import docx
import pandas as pd
import pymupdf
import pytest
from docx.oxml.ns import qn
from docx.shared import Pt

from officeflow.engines.word import convert
from officeflow.engines.word.document import iter_paragraphs, open_docx
from tests.conftest import make_xlsx


def make_template(path: Path) -> Path:
    document = docx.Document()
    p = document.add_paragraph()
    p.add_run("Dear ")
    bold = p.add_run("{{No")       # placeholder split over runs, as Word often does
    bold.bold = True
    p.add_run("m}}, amount: {{ Montant }} MAD")
    document.add_paragraph("العميل: {{الاسم}}")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Ref"
    table.cell(0, 1).text = "{{Référence}}"
    document.sections[0].header.paragraphs[0].text = "Document {{n}} — {{Unknown}}"
    document.save(path)
    return path


def text_of(path: Path) -> str:
    return "\n".join(p.text for p in iter_paragraphs(open_docx(path)))


def test_generate_documents_from_excel(tmp_path, run):
    template = make_template(tmp_path / "t.docx")
    data = make_xlsx(tmp_path / "data.xlsx", [
        {"nom": "Ali", "Montant": 1500.0, "Reference": "2024/01/005", "الإسم": "محمد"},
        {"nom": "Sara", "Montant": 20.5, "Reference": "2024/01/006", "الإسم": "فاطمة"},
        {"nom": None, "Montant": None, "Reference": None, "الإسم": None}])
    outcome = run("word.generate", [data], {"template": str(template), "file_name": "Lettre {{nom}} {{n}}"})
    assert outcome.status == "warning"  # {{Unknown}} matches no column
    assert [p.name for p in outcome.result.outputs] == ["Lettre Ali 001.docx", "Lettre Sara 002.docx"]
    text = text_of(outcome.result.outputs[0])
    assert "Dear Ali, amount: 1500 MAD" in text
    assert "العميل: محمد" in text and "2024/01/005" in text
    assert "Document 1 — {{Unknown}}" in text
    first = open_docx(outcome.result.outputs[0]).paragraphs[0]
    assert [r.text for r in first.runs if r.bold] == ["Ali"]       # formatting of the placeholder kept


def test_generate_requires_existing_template_and_placeholders(tmp_path, run):
    data = make_xlsx(tmp_path / "d.xlsx", [{"a": 1}])
    assert "file not found" in run("word.generate", [data], {"template": str(tmp_path / "x.docx")}).result.summary
    plain = tmp_path / "plain.docx"
    docx.Document().save(plain)
    outcome = run("word.generate", [data], {"template": str(plain)}, out="o2")
    assert "contains no {{placeholder}}" in outcome.result.errors[0]


def test_replace_text_across_runs_headers_and_tables(tmp_path, run):
    template = make_template(tmp_path / "t.docx")
    outcome = run("word.replace", [template], {"find": "{{Nom}}", "replace": "Omar"})
    assert outcome.result.rows == [["t.docx", "1"]]
    assert "Dear Omar," in text_of(outcome.result.outputs[0])
    regex = run("word.replace", [template], {"find": r"\{\{\s*(\w+)\s*\}\}", "replace": r"[\1]", "regex": True},
                out="o2")
    text = text_of(regex.result.outputs[0])
    assert "[Nom]" in text and "[Montant]" in text and "[الاسم]" in text and "Document [n]" in text


def test_merge_documents_keeps_pictures(tmp_path, run):
    image = tmp_path / "dot.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
    pix.save(image)
    first, second = docx.Document(), docx.Document()
    first.add_paragraph("First document")
    second.add_paragraph("Second document")
    second.add_picture(str(image))
    second.add_table(rows=1, cols=1).cell(0, 0).text = "cell"
    first.save(tmp_path / "1.docx")
    second.save(tmp_path / "2.docx")
    outcome = run("word.merge", [tmp_path / "1.docx", tmp_path / "2.docx"], {"output_name": "All"})
    assert outcome.status == "success", outcome.result.errors
    merged = open_docx(outcome.result.outputs[0])
    texts = [p.text for p in merged.paragraphs if p.text]
    assert texts == ["First document", "Second document"]
    assert merged.tables[0].cell(0, 0).text == "cell"
    assert len(merged.inline_shapes) == 1
    assert run("word.merge", [tmp_path / "1.docx"], out="o2").status == "failed"


def test_tables_text_and_format(tmp_path, run):
    document = docx.Document()
    document.add_paragraph("Rapport")
    document.add_paragraph("")
    document.add_paragraph("هذا نص عربي")
    table = document.add_table(rows=2, cols=2)
    for r, row in enumerate([["Ref", "Total"], ["001", "10"]]):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    path = tmp_path / "r.docx"
    document.save(path)
    tables = run("word.tables", [path])
    assert pd.read_excel(tables.result.outputs[0], dtype=str).to_dict("list") == {"Ref": ["001"], "Total": ["10"]}
    text = run("word.text", [path], out="o2").result.outputs[0].read_text(encoding="utf-8")
    assert text.startswith("Rapport") and "هذا نص عربي" in text
    formatted = run("word.format", [path], {"font": "Arial", "size": 12}, out="o3").result
    assert formatted.rows[0][1] == "6 paragraph(s) formatted, 1 empty removed, 1 set right-to-left"
    out = open_docx(formatted.outputs[0])
    assert out.styles["Normal"].font.size == Pt(12)
    arabic = next(p for p in out.paragraphs if "عربي" in p.text)
    assert arabic._p.pPr.find(qn("w:bidi")) is not None


@pytest.mark.skipif(convert.find_libreoffice() is None, reason="LibreOffice not installed")
def test_word_to_pdf(tmp_path, run):
    document = docx.Document()
    document.add_paragraph("Bonjour 2024/01/005")
    document.save(tmp_path / "a.docx")
    (tmp_path / "bad.docx").write_bytes(b"nope")
    outcome = run("word.pdf", [tmp_path])
    assert [p.name for p in outcome.result.outputs] == ["a.pdf"]
    assert "Bonjour 2024/01/005" in pymupdf.open(outcome.result.outputs[0])[0].get_text()
    assert any("bad.docx" in e for e in outcome.result.errors)


def test_excel_to_word_to_pdf_workflow(tmp_path):
    if convert.find_libreoffice() is None:
        pytest.skip("LibreOffice not installed")
    from officeflow.core.operation import OperationContext
    from officeflow.core.workflow import Step, Workflow, run_workflow

    template = make_template(tmp_path / "t.docx")
    make_xlsx(tmp_path / "in" / "d.xlsx", [{"Nom": " Ali ", "Montant": 5, "Reference": "R1", "الاسم": "x"}])
    workflow = Workflow("Letters", [Step("excel.clean"), Step("word.generate", {"template": str(template)}),
                                    Step("word.pdf"), Step("pdf.text")])
    outcome = run_workflow(workflow, [tmp_path / "in"], OperationContext(tmp_path / "out"))
    assert outcome.status == "warning", outcome.summary          # {{Unknown}} stays unfilled
    assert [name for name, _ in outcome.steps] == [
        "Clean and normalize data", "Generate documents from Excel", "Convert Word to PDF", "Extract PDF text"]
    assert "Dear Ali, amount: 5 MAD" in outcome.outputs[0].read_text(encoding="utf-8")


def test_excel_tables_to_word_without_template(tmp_path, run):
    path = tmp_path / "data.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"Ref": ["007", "008"], "Total": [10, 20.5]}).to_excel(writer, sheet_name="Invoices", index=False)
        pd.DataFrame({"الاسم": ["علي"], "المبلغ": [5]}).to_excel(writer, sheet_name="Arabic", index=False)
    outcome = run("word.from_excel", [path])
    assert outcome.status == "success", outcome.result.summary
    document = open_docx(outcome.result.outputs[0])
    assert [p.text for p in document.paragraphs if p.style.name.startswith("Heading")] == ["Invoices", "Arabic"]
    first, second = document.tables
    assert [[c.text for c in row.cells] for row in first.rows] == [["Ref", "Total"], ["007", "10"], ["008", "20.5"]]
    assert first.rows[0].cells[0].paragraphs[0].runs[0].bold
    assert second._tbl.tblPr.find(qn("w:bidiVisual")) is not None          # Arabic table reads right to left


def test_pdf_tables_to_word_and_workflow_chain(tmp_path, run):
    from officeflow.core.registry import get
    from officeflow.core.workflow import Step, Workflow

    path = tmp_path / "t.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        rows = [["Ref", "Client", "Total"], ["001", "Ali", "10"], ["002", "Sara", "20"]]
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                rect = pymupdf.Rect(72 + c * 100, 72 + r * 24, 172 + c * 100, 96 + r * 24)
                page.draw_rect(rect)
                page.insert_text((rect.x0 + 4, rect.y0 + 16), value)
        doc.save(path)
    outcome = run("pdf.tables_word", [path])
    document = open_docx(outcome.result.outputs[0])
    assert outcome.result.outputs[0].name == "t - tables.docx"
    assert [[c.text for c in row.cells] for row in document.tables[0].rows] == rows
    assert document.paragraphs[0].text == "Page 1 – Table 1"
    # PDF → Excel → Word is also a valid chain now, with no template.
    assert get("pdf.tables_word").output_extensions == (".docx",)
    Workflow("Tables", [Step("pdf.tables"), Step("word.from_excel")]).validate()
