from pathlib import Path

import openpyxl
import pandas as pd
import pymupdf
import pytest

from officeflow.engines.pdf import organizer, pages
from officeflow.engines.pdf.reader import PdfError, iter_page_texts, open_pdf
from tests.conftest import make_pdf

PATTERN = r"\b\d{4}/\d{2}/\d{3}\b"


@pytest.fixture
def collection(tmp_path):
    """Two source folders, like the example in the specification."""
    a, b = tmp_path / "Folder A", tmp_path / "Folder B"
    make_pdf(a / "invoice.pdf", ["Invoice ref 2024/01/005"])
    make_pdf(a / "letter.pdf", ["Nothing to see"])
    make_pdf(a / "both.pdf", ["Ref 2024/01/005", "see also 2024/02/123"])
    make_pdf(b / "invoice.pdf", ["Delivery note for 2024/01/005 ..."])
    make_pdf(b / "sub" / "contract.pdf", ["Contract 2024/02/123"])
    (b / "copy of contract.pdf").write_bytes((b / "sub" / "contract.pdf").read_bytes())
    (b / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 100), "Secret 2024/09/999")
        doc.save(b / "locked.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="o")
    return [a, b]


def tree(root: Path) -> dict[str, list[str]]:
    return {d.name: sorted(f.name for f in d.iterdir()) for d in sorted(root.iterdir()) if d.is_dir()}


def test_organizer_groups_files_from_several_folders(collection, tmp_path, run):
    before = {p: p.read_bytes() for folder in collection for p in folder.rglob("*.pdf")}
    outcome = run("pdf.organize", collection)
    assert tree(tmp_path / "out") == {
        "2024-01-005": ["both.pdf", "invoice (2).pdf", "invoice.pdf"],
        "2024-02-123": ["both.pdf", "copy of contract.pdf"],
        "_No match": ["letter.pdf"],
        "_Unreadable": ["broken.pdf", "locked.pdf"],
    }
    assert outcome.status == "warning"
    assert any("locked.pdf: password-protected" in e for e in outcome.result.errors)
    assert any("broken.pdf" in e for e in outcome.result.errors)
    assert any("contract.pdf: Identical to copy of contract.pdf" in w for w in outcome.result.warnings)
    report = pd.read_excel(tmp_path / "out" / "Organizer report.xlsx")
    assert len(report) == 8 and set(report["Status"]) == {
        "Matched", "Several values", "No match", "Duplicate", "Unreadable"}
    # originals untouched
    assert all(p.read_bytes() == data for p, data in before.items())


def test_organizer_preview_writes_nothing(collection, tmp_path):
    from officeflow.core import registry
    from officeflow.core.operation import OperationContext
    from officeflow.core.runner import preview_operation

    preview = preview_operation(registry.get("pdf.organize"), collection, {}, OperationContext(tmp_path / "out"))
    assert not (tmp_path / "out").exists()
    assert len(preview.rows) == 8 and "2 folder(s)" in preview.summary


def test_organizer_policies_rename_and_rerun(collection, tmp_path, run):
    params = {"multi_match": "separate", "unmatched": "skip", "duplicates": "folder",
              "rename_template": "{value} - {folder} - {name}"}
    run("pdf.organize", collection, params)
    expected = {
        "2024-01-005": ["2024-01-005 - Folder A - invoice.pdf", "2024-01-005 - Folder B - invoice.pdf"],
        "2024-02-123": ["2024-02-123 - Folder B - copy of contract.pdf"],
        "_Duplicates": ["contract.pdf"],
        "_Multiple matches": ["both.pdf"],
    }
    assert tree(tmp_path / "out") == expected
    # Running again must not overwrite: new files get a numbered name.
    run("pdf.organize", collection, params)
    assert tree(tmp_path / "out")["_Multiple matches"] == ["both (2).pdf", "both.pdf"]
    first = run("pdf.organize", collection, {"multi_match": "first"}, out="o2")
    assert "both.pdf" not in tree(tmp_path / "o2")["2024-02-123"]
    assert first.status == "warning"


def test_organizer_move_and_output_inside_source(tmp_path, run):
    src = tmp_path / "in"
    make_pdf(src / "a.pdf", ["x 2024/01/005"])
    from officeflow.core import registry
    from officeflow.core.operation import OperationContext
    from officeflow.core.runner import run_operation

    for _ in range(2):  # second run: sorted output inside the source is not re-read
        outcome = run_operation(registry.get("pdf.organize"), [src], {"move": True},
                                OperationContext(src / "sorted"))
    assert not (src / "a.pdf").exists()
    assert tree(src / "sorted") == {"2024-01-005": ["a.pdf"]}
    assert outcome.status == "failed" and "0 found" in outcome.result.summary


def test_organizer_invalid_pattern_and_template(collection, run):
    assert "Invalid pattern" in run("pdf.organize", collection, {"patterns": "(["}).result.summary
    assert "Invalid file name template" in run(
        "pdf.organize", collection, {"rename_template": "{oops}"}).result.summary


def test_capture_group_and_multiple_patterns():
    options = organizer.OrganizerOptions([r"Ref[:\s]+(\w+)", r"N° (?P<value>\d+)"])
    patterns = organizer.compile_patterns(options)
    assert organizer.find_values("ref: AB12 … N° 77 … REF  ab12", patterns) == ["AB12", "ab12", "77"]


def test_values_differing_only_by_case_share_a_folder(tmp_path, run):
    make_pdf(tmp_path / "in" / "1.pdf", ["Ref: AB12"])
    make_pdf(tmp_path / "in" / "2.pdf", ["ref: ab12"])
    run("pdf.organize", [tmp_path / "in"], {"patterns": r"ref: (\w+)"})
    assert tree(tmp_path / "out") == {"AB12": ["1.pdf", "2.pdf"]}


def test_arabic_and_french_pdfs_group_together(tmp_path, run):
    make_pdf(tmp_path / "in" / "عقد.pdf", ['<p dir="rtl">مرجع الملف ٢٠٢٤/٠١/٠٠٥ فاتورة</p>'], html=True)
    make_pdf(tmp_path / "in" / "facture.pdf", ["<p>Référence 2024/01/005 — Société Générale</p>"], html=True)
    make_pdf(tmp_path / "in" / "نص.pdf", ['<p dir="rtl">وصل رقم 77 بتاريخ اليوم</p>'], html=True)
    text = "".join(iter_page_texts(tmp_path / "in" / "عقد.pdf"))
    assert "٢٠٢٤/٠١/٠٠٥" in text  # digit run restored to reading order
    run("pdf.organize", [tmp_path / "in"], {"patterns": PATTERN + "\n" + r"رقم\s*(\d+)"})
    assert tree(tmp_path / "out") == {"2024-01-005": ["facture.pdf", "عقد.pdf"], "77": ["نص.pdf"]}
    kept = run("pdf.organize", [tmp_path / "in"], {"western_digits": False}, out="o2")
    assert tree(tmp_path / "o2") == {"2024-01-005": ["facture.pdf"], "_No match": ["نص.pdf"], "٢٠٢٤-٠١-٠٠٥": ["عقد.pdf"]}
    assert kept.status == "warning"


def test_batch_rename(collection, tmp_path, run):
    run("pdf.rename", [collection[0]], {"rename_template": "{value}_{n}"})
    out = tmp_path / "out"
    assert sorted(p.name for p in out.glob("*.pdf")) == ["2024-01-005_001.pdf", "2024-01-005_002.pdf"]
    assert [p.name for p in (out / "_No match").iterdir()] == ["letter.pdf"]


def test_open_pdf_errors(collection):
    with pytest.raises(PdfError, match="password-protected"):
        open_pdf(collection[1] / "locked.pdf")
    with pytest.raises(PdfError, match="damaged"):
        open_pdf(collection[1] / "broken.pdf")


def test_page_ranges():
    assert pages.parse_page_ranges("1-3, 5, 9-", 10) == [0, 1, 2, 4, 8, 9]
    assert pages.parse_page_ranges("٢،٤", 10) == [1, 3]
    assert pages.parse_page_ranges("-2 50", 10) == [0, 1]
    for bad in ("a", "3-1", "0"):
        with pytest.raises(Exception, match="Invalid page range"):
            pages.parse_page_ranges(bad, 10)


def test_merge_split_extract(tmp_path, run):
    a = make_pdf(tmp_path / "a.pdf", ["A1", "A2", "A3"])
    b = make_pdf(tmp_path / "b.pdf", ["B1"])
    (tmp_path / "bad.pdf").write_bytes(b"nope")
    merged = run("pdf.merge", [a, tmp_path / "bad.pdf", b], {"output_name": "All"})
    assert merged.status == "warning"
    with pymupdf.open(merged.result.outputs[0]) as doc:
        assert doc.page_count == 4 and [t[1] for t in doc.get_toc()] == ["a", "b"]
        assert doc[3].get_text().strip() == "B1"
    split = run("pdf.split", [a], {"pages_per_file": 2}, out="o2")
    assert [p.name for p in split.result.outputs] == ["a - p1-2.pdf", "a - p3.pdf"]
    extracted = run("pdf.pages", [a, b], {"pages": "2-"}, out="o3")
    assert [p.name for p in extracted.result.outputs] == ["a - pages.pdf"]
    assert "b.pdf: has 1 page(s)" in extracted.result.errors[0]
    with pymupdf.open(extracted.result.outputs[0]) as doc:
        assert [p.get_text().strip() for p in doc] == ["A2", "A3"]
    assert run("pdf.pages", [a], {"pages": "x"}, out="o4").status == "failed"


def test_text_search_and_compare(tmp_path, run):
    a = make_pdf(tmp_path / "a.pdf", ["Total amount 100 MAD\nSigned in Rabat", "Page two"])
    b = make_pdf(tmp_path / "b.pdf", ["Total amount 250 MAD\nSigned in Rabat", "Page two"])
    scan = tmp_path / "scan.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(scan)
    text = run("pdf.text", [a, scan])
    assert "===== Page 2 =====\nPage two" in text.result.outputs[0].read_text(encoding="utf-8")
    assert "scan.pdf: no text found" in text.result.warnings[0]
    found = run("pdf.search", [tmp_path], {"find": r"amount (\d+)", "regex": True}, out="o2")
    assert [r[:3] for r in found.result.rows] == [["a.pdf", "1", "amount 100"], ["b.pdf", "1", "amount 250"]]
    assert len(pd.read_excel(found.result.outputs[0])) == 2
    diff = run("pdf.compare", [a, b], out="o3")
    html = diff.result.outputs[0].read_text(encoding="utf-8")
    assert "1 differing line(s)" in diff.result.summary and "diff_chg" in html
    c = make_pdf(tmp_path / "c.pdf", ["Total amount 100 MAD\nSigned in Rabat", "Page two"])
    assert "identical" in run("pdf.compare", [a, c], out="o4").result.summary


def test_tables_to_excel(tmp_path, run):
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
    outcome = run("pdf.tables", [path, make_pdf(tmp_path / "plain.pdf", ["no table"])])
    frame = pd.read_excel(outcome.result.outputs[0], dtype=str)
    assert frame.to_dict("list") == {"Ref": ["001", "002"], "Client": ["Ali", "Sara"], "Total": ["10", "20"]}
    assert "plain.pdf: no table detected." in outcome.result.warnings


def _photo_pdf(path: Path) -> Path:
    """A PDF holding one large, noisy photo-like image (compresses well when downsampled)."""
    import random
    import zlib

    random.seed(1)
    width = height = 1200
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            v = (x * 3 + y * 5 + random.randint(0, 40)) % 256
            raw += bytes((v, (v * 7) % 256, (255 - v)))
    def chunk(kind: bytes, data: bytes) -> bytes:
        import struct
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    import struct
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 60), "Ref 2024/01/005")
        page.insert_image(pymupdf.Rect(72, 80, 372, 380), stream=png)
        doc.save(path)
    return path


def test_compress_pdfs_writes_smaller_copies(tmp_path, run):
    source = _photo_pdf(tmp_path / "in" / "scan.pdf")
    before = source.read_bytes()
    outcome = run("pdf.compress", [source], {"level": "strong"})
    assert outcome.status == "success", outcome.result.summary
    out = outcome.result.outputs[0]
    assert out.name == "scan.pdf" and out.parent != source.parent
    assert out.stat().st_size < len(before) * 0.7
    assert source.read_bytes() == before                                   # original untouched
    assert "2024/01/005" in next(iter_page_texts(out))
    # a file that cannot get smaller is copied as it is, never made bigger
    tiny = make_pdf(tmp_path / "in2" / "tiny.pdf", ["x"])
    again = run("pdf.compress", [tiny], {"level": "lossless"}, out="out2")
    assert again.result.outputs[0].stat().st_size <= tiny.stat().st_size


def test_values_to_excel_one_row_per_pdf(tmp_path, run):
    folder = tmp_path / "in"
    make_pdf(folder / "a.pdf", ["Invoice 2024/01/005 dated 03/02/2024 Total: 1,250.00", "again 2024/01/005"])
    make_pdf(folder / "b.pdf", ["Invoice 2024/01/006 no date"])
    params = {"fields": "Reference: \\b\\d{4}/\\d{2}/\\d{3}\\b\nDate: \\b\\d{2}/\\d{2}/\\d{4}\\b\n"
                        "Total: Total\\s*:?\\s*([\\d.,]+)", "output_name": "Invoices"}
    preview = registry_get("pdf.values").preview(sorted(folder.glob("*.pdf")), registry_get("pdf.values").clean_params(params),
                                                 _ctx(tmp_path))
    assert preview.headers == ["File", "Reference", "Date", "Total"]
    outcome = run("pdf.values", [folder], params)
    assert outcome.status == "warning"                                     # b.pdf has no date or total
    frame = pd.read_excel(outcome.result.outputs[0], dtype=str).fillna("")
    assert list(frame.columns) == ["File", "Reference", "Date", "Total", "Pages", "File date", "Processed on", "Folder"]
    assert frame.loc[0, ["File", "Reference", "Date", "Total", "Pages"]].tolist() == ["a.pdf", "2024/01/005", "03/02/2024", "1,250.00", "2"]
    assert frame.loc[1, ["File", "Reference", "Date"]].tolist() == ["b.pdf", "2024/01/006", ""]
    assert outcome.result.outputs[0].name == "Invoices.xlsx"


def test_workflow_keeps_files_of_a_marked_step(tmp_path):
    from officeflow.core.operation import OperationContext
    from officeflow.core.workflow import Step, Workflow, run_workflow

    _photo_pdf(tmp_path / "in" / "scan.pdf")
    workflow = Workflow("Compress and list", [Step("pdf.compress", {}, keep=True),
                                             Step("pdf.values", {"fields": "Ref: \\d{4}/\\d{2}/\\d{3}"})])
    assert Workflow.from_dict(workflow.to_dict()).steps[0].keep
    outcome = run_workflow(workflow, [tmp_path / "in"], OperationContext(tmp_path / "out"))
    assert outcome.status == "success", outcome.summary
    names = sorted(p.name for p in outcome.result_dir.iterdir())
    assert names == ["Extracted values.xlsx", "scan.pdf"]
    assert sorted(p.name for p in outcome.outputs) == names
    frame = pd.read_excel(outcome.result_dir / "Extracted values.xlsx", dtype=str)
    assert frame.loc[0, "Ref"] == "2024/01/005"
    assert not list((tmp_path / "out").glob(".officeflow-work-*"))


def registry_get(op_id):
    from officeflow.core import registry
    return registry.get(op_id)


def _ctx(tmp_path):
    from officeflow.core.operation import OperationContext
    return OperationContext(tmp_path / "preview")
