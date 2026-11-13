"""Smoke tests for the desktop interface (run headless)."""

import os
import time

import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.conftest import make_pdf, make_xlsx  # noqa: E402


@pytest.fixture
def window():
    from officeflow.app import create

    app, win = create(["officeflow"])
    win.resize(1440, 900)
    win.show()
    yield win
    win.close()
    win.ctx.db.close()


def wait(panel, timeout=20):
    deadline = time.time() + timeout
    while panel.is_busy() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        QApplication.processEvents()
    assert not panel.is_busy()


def test_every_page_and_tool_opens(window):
    from officeflow.core import registry

    for key in ("dashboard", "excel", "pdf", "word", "workflow", "history", "logs", "settings"):
        window.navigate(key)
        assert window.current_page() == key
    for op in registry.all_operations():
        window.open_tool(op.id)
    window._theme_requested("light")
    window.navigate("dashboard")
    assert window.ctx.settings.theme == "light"


def test_organizer_preview_and_run_from_the_gui(window, tmp_path):
    make_pdf(tmp_path / "A" / "x.pdf", ["Ref 2024/01/005"])
    make_pdf(tmp_path / "B" / "y.pdf", ["Ref 2024/01/005"])
    window.open_tool("pdf.organize")
    page = window._pages["pdf"]._pages["pdf.organize"]
    page.inputs.add_paths([tmp_path / "A", tmp_path / "B"])
    page.panel.output.setText(str(tmp_path / "out"))

    page.preview()
    wait(page.panel)
    assert page.panel.banner_title.text().startswith("Preview")
    assert page.panel.table.rowCount() == 2 and not (tmp_path / "out").exists()

    page.run()
    wait(page.panel)
    assert page.panel.banner_title.text() == "Done"
    assert sorted(p.name for p in (tmp_path / "out" / "2024-01-005").iterdir()) == ["x.pdf", "y.pdf"]
    window.navigate("dashboard")
    assert window.ctx.db.list_runs()[0].target_id == "pdf.organize"


def test_missing_inputs_show_a_message(window):
    window.open_tool("excel.clean")
    page = window._pages["excel"]._pages["excel.clean"]
    page.run()
    assert page.panel.banner_title.text() == "Could not complete"


def test_workflow_builder_save_load_run(window, tmp_path):
    make_xlsx(tmp_path / "in" / "a.xlsx", [{"Ref": "A"}, {"Ref": " a "}])
    window.navigate("workflow")
    page = window._pages["workflow"]
    for op_id in ("excel.clean", "excel.remove_duplicates"):
        page._tools.setCurrentIndex(page._tools.findData(op_id))
        page._add()
    page._form.set_values({"columns": "Ref", "save_removed": False})
    page._name.setText("Tidy")
    page._save()
    assert window.ctx.db.load_workflow("Tidy")["steps"][1]["params"]["columns"] == "Ref"

    page._new()
    page._saved.setCurrentIndex(page._saved.findData("Tidy"))
    page._load_selected()
    assert len(page._steps) == 2
    page.inputs.add_paths([tmp_path / "in"])
    page.panel.output.setText(str(tmp_path / "out"))
    page.run()
    wait(page.panel)
    assert page.panel.banner_title.text() == "Done", page.panel.banner_text.text()
    result = next((tmp_path / "out" / "02 Remove duplicates").glob("*.xlsx"))
    assert pd.read_excel(result)["Ref"].tolist() == ["A"]
