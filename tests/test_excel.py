from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from officeflow.engines.excel import io, transform
from tests.conftest import make_xlsx


def test_merge_matches_differently_named_columns(tmp_path, run):
    make_xlsx(tmp_path / "a.xlsx", [{"Nom Client": "Ali", "Montant": 10, "Prix 2023": 1}])
    make_xlsx(tmp_path / "b.xlsx", [{"nom_client": "Sara", "Montent": 20, "Prix 2024": 2}])
    (tmp_path / "c.csv").write_text("NOM CLIENT;Ville\nOmar;Rabat\n", encoding="utf-8")
    outcome = run("excel.merge_files", [tmp_path / "a.xlsx", tmp_path / "b.xlsx", tmp_path / "c.csv"])
    assert outcome.status == "success", outcome.result.errors
    merged = pd.read_excel(outcome.result.outputs[0])
    assert list(merged.columns) == ["Source", "Nom Client", "Montant", "Prix 2023", "Prix 2024", "Ville"]
    assert merged["Nom Client"].tolist() == ["Ali", "Sara", "Omar"]
    assert merged["Montant"].tolist()[:2] == [10, 20]  # fuzzy: Montent -> Montant


def test_merge_exact_mode_keeps_columns_apart_and_reports_bad_files(tmp_path, run):
    make_xlsx(tmp_path / "a.xlsx", [{"Name": "x"}])
    make_xlsx(tmp_path / "b.xlsx", [{"name": "y"}])
    (tmp_path / "broken.xlsx").write_bytes(b"not a workbook")
    outcome = run("excel.merge_files", [tmp_path], {"matching": "exact", "add_source": False})
    assert outcome.status == "warning" and "broken.xlsx" in outcome.result.errors[0]
    assert list(pd.read_excel(outcome.result.outputs[0]).columns) == ["Name", "name"]


def test_arabic_headers_match_and_sheet_is_rtl(tmp_path, run):
    make_xlsx(tmp_path / "١.xlsx", [{"الإسم": "محمد", "المبلغ": 5}])
    make_xlsx(tmp_path / "٢.xlsx", [{"الاسم": "فاطمة", "المبلغ": 7}])
    outcome = run("excel.merge_files", [tmp_path], {"add_source": False, "output_name": "مدمج"})
    out = outcome.result.outputs[0]
    assert out.name == "مدمج.xlsx"
    sheet = openpyxl.load_workbook(out).active
    assert [c.value for c in sheet[1]] == ["الإسم", "المبلغ"]
    assert sheet.sheet_view.rightToLeft is True and sheet.max_row == 3


def test_merge_sheets(tmp_path, run):
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"A": [1]}).to_excel(writer, sheet_name="Jan", index=False)
        pd.DataFrame({"a": [2]}).to_excel(writer, sheet_name="Feb", index=False)
    merged = pd.read_excel(run("excel.merge_sheets", [path]).result.outputs[0])
    assert merged.to_dict("list") == {"Sheet": ["Jan", "Feb"], "A": [1, 2]}


def test_remove_duplicates_loose_and_subset(tmp_path, run):
    make_xlsx(tmp_path / "d.xlsx", [
        {"Ref": "A-1", "Name": "Ali"}, {"Ref": " a-1 ", "Name": "ALI"},
        {"Ref": "٢٠", "Name": "x"}, {"Ref": "20", "Name": "y"}, {"Ref": "B", "Name": "z"}])
    outcome = run("excel.remove_duplicates", [tmp_path / "d.xlsx"], {"columns": "ref"})
    sheets = pd.read_excel(outcome.result.outputs[0], sheet_name=None)
    assert sheets["Data"]["Name"].tolist() == ["Ali", "x", "z"]
    assert len(sheets["Removed duplicates"]) == 2
    strict, _ = transform.remove_duplicates(pd.read_excel(tmp_path / "d.xlsx"), loose=False)
    assert len(strict) == 5


def test_unknown_column_gives_helpful_error(tmp_path, run):
    make_xlsx(tmp_path / "d.xlsx", [{"Ref": 1}])
    outcome = run("excel.remove_duplicates", [tmp_path / "d.xlsx"], {"columns": "Nope"})
    assert outcome.status == "warning"
    assert "Column “Nope” not found. Available columns: Ref" in outcome.result.errors[0]


def test_clean(tmp_path, run):
    make_xlsx(tmp_path / "c.xlsx", [
        {" Name ": "  Ali   Ben‏ ", "Code": "٠١٢", "Empty": None},
        {" Name ": None, "Code": None, "Empty": None},
        {" Name ": "x y", "Code": "7", "Empty": None}])
    outcome = run("excel.clean", [tmp_path / "c.xlsx"],
                  {"western_digits": True, "drop_empty_columns": True, "text_case": "upper"})
    cleaned = pd.read_excel(outcome.result.outputs[0], dtype=str)
    assert cleaned.to_dict("list") == {"Name": ["ALI BEN", "X Y"], "Code": ["012", "7"]}


def test_split_to_files_and_sheets(tmp_path, run):
    src = make_xlsx(tmp_path / "s.xlsx", [
        {"Dept": "Sales/EU", "V": 1}, {"Dept": "HR", "V": 2}, {"Dept": "Sales/EU", "V": 3}, {"Dept": None, "V": 4}])
    outcome = run("excel.split", [src], {"column": "dept"})
    assert sorted(p.name for p in outcome.result.outputs) == ["(blank).xlsx", "HR.xlsx", "Sales-EU.xlsx"]
    assert pd.read_excel(tmp_path / "out" / "s" / "Sales-EU.xlsx")["V"].tolist() == [1, 3]
    book = run("excel.split", [src], {"column": "Dept", "target": "sheets"}, out="o2").result.outputs[0]
    assert openpyxl.load_workbook(book).sheetnames == ["Sales-EU", "HR", "(blank)"]


def test_compare_with_keys(tmp_path, run):
    a = make_xlsx(tmp_path / "a.xlsx", [{"Ref": "1", "Amount": 10, "City": "Fes"}, {"Ref": "2", "Amount": 5, "City": "Rabat"}])
    b = make_xlsx(tmp_path / "b.xlsx", [{"ref": "2", "Amount": 6, "City": "Rabat"}, {"ref": "3", "Amount": 1, "City": "Oujda"}])
    outcome = run("excel.compare", [a, b], {"keys": "Ref"})
    sheets = pd.read_excel(outcome.result.outputs[0], sheet_name=None, dtype=str)
    assert sheets["Only in first"]["Ref"].tolist() == ["1"]
    assert sheets["Only in second"]["Ref"].tolist() == ["3"]
    assert sheets["Changed cells"].values.tolist() == [["2", "Amount", "5", "6"]]
    copy = make_xlsx(tmp_path / "a2.xlsx", pd.read_excel(a, dtype=object).to_dict("records"))
    same = run("excel.compare", [a, copy], out="o2")
    assert same.result.summary == "The two files are identical."
    assert run("excel.compare", [a], out="o3").status == "failed"


def test_replace_preserves_formatting_formulas_and_original(tmp_path, run):
    src = tmp_path / "r.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Ville", "Total"])
    sheet.append(["casablanca nord", 5])
    sheet.append(["Casablanca", "=B2*2"])
    sheet["A2"].font = openpyxl.styles.Font(bold=True, color="FF0000")
    book.save(src)
    before = src.read_bytes()
    outcome = run("excel.replace", [src], {"find": "casablanca", "replace": "الدار البيضاء"})
    assert outcome.result.rows == [["r.xlsx", "2"]]
    out = openpyxl.load_workbook(outcome.result.outputs[0]).active
    assert out["A2"].value == "الدار البيضاء nord" and out["A2"].font.bold
    assert out["B3"].value == "=B2*2"
    assert src.read_bytes() == before
    whole = run("excel.replace", [src], {"find": "Casablanca", "replace": "X", "whole_cell": True,
                                         "case_sensitive": True}, out="o2")
    assert whole.result.rows == [["r.xlsx", "1"]]
    regex = run("excel.replace", [src], {"find": r"(\w+) nord", "replace": r"\1 N", "regex": True}, out="o3")
    assert openpyxl.load_workbook(regex.result.outputs[0]).active["A2"].value == "casablanca N"
    assert run("excel.replace", [src], {"find": "(", "regex": True}, out="o4").status == "failed"


def test_extract_rows(tmp_path, run):
    make_xlsx(tmp_path / "a.xlsx", [{"Ref": "2024/01", "N": "a"}, {"Ref": "2023/09", "N": "b"}])
    make_xlsx(tmp_path / "b.xlsx", [{"ref": "٢٠٢٤/٠٥", "N": "c"}])
    outcome = run("excel.extract", [tmp_path], {"column": "Ref", "mode": "regex", "value": r"^2024/", "keep_columns": "N"})
    assert pd.read_excel(outcome.result.outputs[0]).to_dict("list") == {
        "Source": ["a.xlsx", "b.xlsx"], "N": ["a", "c"]}
    assert run("excel.extract", [tmp_path], {"column": "Ref"}, out="o2").status == "failed"


def test_report_totals_and_summary(tmp_path, run):
    src = make_xlsx(tmp_path / "r.xlsx", [{"Dept": "A", "Amount": 10}, {"Dept": "B", "Amount": 5}, {"Dept": "A", "Amount": 1}])
    out = run("excel.report", [src], {"group_by": "dept"}).result.outputs[0]
    book = openpyxl.load_workbook(out)
    report = book["Report"]
    assert [c.value for c in report[5]] == ["Total", 16] and report["A5"].font.bold
    assert report.freeze_panes == "A2" and report.auto_filter.ref == "A1:B4"
    assert [[c.value for c in r] for r in book["Summary"].iter_rows(min_row=2)] == [["A", 2, 11], ["B", 1, 5]]


def test_convert_both_ways_with_legacy_encodings(tmp_path, run):
    (tmp_path / "ar.csv").write_bytes("الاسم;الرمز\nمحمد;007\n".encode("cp1256"))
    (tmp_path / "fr.csv").write_bytes("Prénom,Ville\nRené,Fès\n".encode("cp1252"))
    outcome = run("excel.convert", [tmp_path])
    by_name = {p.name: pd.read_excel(p, dtype=str) for p in outcome.result.outputs}
    assert by_name["ar.xlsx"].to_dict("list") == {"الاسم": ["محمد"], "الرمز": ["007"]}
    assert by_name["fr.xlsx"].to_dict("list") == {"Prénom": ["René"], "Ville": ["Fès"]}
    back = run("excel.convert", [outcome.result.outputs[0]], {"delimiter": ";"}, out="o2").result.outputs[0]
    assert back.read_text(encoding="utf-8-sig").splitlines() == ["الاسم;الرمز", "محمد;007"]


def test_read_table_sheet_selection_and_errors(tmp_path):
    path = tmp_path / "b.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"A": [1]}).to_excel(writer, sheet_name="One", index=False)
        pd.DataFrame({"B": [2]}).to_excel(writer, sheet_name="Two", index=False)
    assert list(io.read_table(path, "Two").columns) == ["B"]
    assert list(io.read_table(path, "2").columns) == ["B"]
    with pytest.raises(Exception, match="no sheet “X”. Available: One, Two"):
        io.read_table(path, "X")
    (tmp_path / "old.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(Exception, match="save it as .xlsx"):
        io.sheet_names(tmp_path / "old.xls")


def test_sheet_title_is_valid_and_unique():
    taken: set[str] = set()
    assert io.sheet_title("a/b:c", taken) == "a-b-c"
    assert io.sheet_title("A/B:C", taken) == "A-B-C (2)"
    assert len(io.sheet_title("x" * 50)) == 31
