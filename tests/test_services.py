from pathlib import Path

from officeflow.services import files, textnorm
from officeflow.services.database import Database
from officeflow.services.settings import Settings
from datetime import datetime


def test_safe_filename_handles_slashes_arabic_and_reserved_names():
    assert files.safe_filename("2024/01/005") == "2024-01-005"
    assert files.safe_filename("فاتورة رقم ١٢/٣") == "فاتورة رقم ١٢-٣"
    assert files.safe_filename("CON") == "_CON"
    assert files.safe_filename('  a:b*c?.  ') == "a-b-c-"
    assert files.safe_filename("///") == "---"
    assert files.safe_filename("‏") == "_"


def test_unique_path_never_overwrites(tmp_path):
    (tmp_path / "a.pdf").write_text("x")
    taken: set[Path] = set()
    first = files.unique_path(tmp_path / "a.pdf", taken)
    second = files.unique_path(tmp_path / "a.pdf", taken)
    assert first.name == "a (2).pdf" and second.name == "a (3).pdf"


def test_collect_files_filters_recurses_and_deduplicates(tmp_path):
    (tmp_path / "sub").mkdir()
    for name in ("b.pdf", "a.PDF", "note.txt", "~$lock.pdf", "sub/c.pdf", "sub/ملف.pdf"):
        (tmp_path / name).write_text("x")
    found = files.collect_files([tmp_path, tmp_path / "b.pdf"], (".pdf",))
    assert [p.name for p in found] == ["a.PDF", "b.pdf", "c.pdf", "ملف.pdf"]
    assert len(files.collect_files([tmp_path], (".pdf",), recursive=False)) == 2


def test_text_normalisation():
    assert textnorm.to_western_digits("٢٠٢٤/۰۱") == "2024/01"
    assert textnorm.fix_reversed_digit_runs("مرجع ٥٠٠/١٠/٤٢٠٢ و 2024") == "مرجع ٢٠٢٤/٠١/٠٠٥ و 2024"
    # presentation forms (as stored in PDFs) fold back to normal letters
    assert textnorm.normalize_text("ﻣﺮﺟﻊ") == "مرجع"
    assert textnorm.normalize_text("a‏b c") == "ab c"
    assert textnorm.header_key(" Nom_Client ") == textnorm.header_key("NOM CLIENT") == "nomclient"
    assert textnorm.header_key("Référence") == textnorm.header_key("reference")
    assert textnorm.header_key("الإسم") == textnorm.header_key("الاسم")
    assert textnorm.split_list("أ، ب,c ; d") == ["أ", "ب", "c", "d"]


def test_database_history_and_workflows(tmp_path):
    db = Database(tmp_path / "t.db")
    db.add_run(kind="operation", target_id="x", name="X", started_at=datetime.now(), duration_s=1.2,
               status="success", input_count=3, output_count=1, output_dir=tmp_path, summary="ok",
               details={"params": {"a": "ب"}})
    record = db.list_runs()[0]
    assert record.name == "X" and record.details["params"]["a"] == "ب"
    assert db.stats() == {"runs": 1, "files": 3, "ok": 1}
    db.save_workflow("w", {"name": "w", "steps": []})
    db.save_workflow("w", {"name": "w", "steps": [{"op": "a"}]})
    assert db.list_workflows() == ["w"] and db.load_workflow("w")["steps"] == [{"op": "a"}]
    db.delete_workflow("w")
    assert db.load_workflow("w") is None


def test_settings_roundtrip_and_corrupt_file(tmp_path):
    file = tmp_path / "s.json"
    Settings(theme="light", output_dir="/x").save(file)
    assert Settings.load(file).theme == "light"
    file.write_text("{broken")
    assert Settings.load(file).theme == "dark"
