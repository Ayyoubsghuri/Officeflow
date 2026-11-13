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
    from officeflow.gui.widgets.flow_canvas import START_ID

    make_xlsx(tmp_path / "in" / "a.xlsx", [{"Ref": "A"}, {"Ref": " a "}])
    window.navigate("workflow")
    page = window._pages["workflow"]
    page.add_step("excel.clean")
    page.add_step("excel.remove_duplicates")
    assert list(page.scene.nodes) == [START_ID, *page._uids]          # start node + 2 steps
    assert len(page.scene.edges) == 3                                 # 2 links + link to "Add step"
    page.form.set_values({"columns": "Ref", "save_removed": False})   # edits the selected step
    assert page.steps[1].params["columns"] == "Ref"
    assert page.scene.nodes[page._uids[1]].data_.subtitle == "Columns to compare: Ref"

    page.undo()
    assert page.steps[1].params.get("columns", "") == ""
    page.redo()
    assert page.steps[1].params["columns"] == "Ref"

    page.name_edit.setText("Tidy")
    page.save()
    assert page.badge.text() == "Saved"
    assert window.ctx.db.load_workflow("Tidy")["steps"][1]["params"]["columns"] == "Ref"

    page.new()
    assert page.steps == [] and page.badge.text() == "Draft"
    page.load_named("Tidy")
    assert len(page.steps) == 2 and page.badge.text() == "Saved"
    page.inputs.add_paths([tmp_path / "in"])
    page.panel.output.setText(str(tmp_path / "out"))
    page.run()
    wait(page.panel)
    assert page.panel.banner_title.text() == "Done", page.panel.banner_text.text()
    result = next((tmp_path / "out" / "02 Remove duplicates").glob("*.xlsx"))
    assert pd.read_excel(result)["Ref"].tolist() == ["A"]
    assert [page.scene.nodes[u].data_.status for u in page._uids] == ["success", "success"]


def test_workflow_builder_flags_incompatible_steps(window):
    window.navigate("workflow")
    page = window._pages["workflow"]
    page.new()
    page.add_step("pdf.text")
    page.add_step("pdf.merge")
    merge = page.scene.nodes[page._uids[1]]
    assert merge.data_.warning.startswith("Needs .pdf")
    assert any(edge.broken for edge in page.scene.edges)
    page.move_step(page._uids[1], -1)        # merge first, then extract text: valid
    assert not any(edge.broken for edge in page.scene.edges)
    page.remove_step(page._uids[0])
    assert [s.op_id for s in page.steps] == ["pdf.text"]


def test_folder_fan_keyboard_hover_and_click(window):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    window.navigate("dashboard")
    fan = window._pages["dashboard"].fan
    start = fan.selected_id()
    QTest.keyClick(fan, Qt.Key.Key_Right)
    assert fan.selected_id() != start
    opened = []
    fan.activated.connect(opened.append)
    QTest.keyClick(fan, Qt.Key.Key_Return)
    assert opened == [fan.selected_id()]
    for _ in range(40):  # let the lift animation settle, then click the green folder
        QApplication.processEvents()
        time.sleep(0.02)
    fan.grab()
    card = next(c for c in fan._cards if c.index == fan._selected)
    inside = card.quad.boundingRect().center() + QPointF(card.quad.boundingRect().width() * 0.25, 0)
    assert fan._index_at(QPointF(inside)) == fan._selected
    QTest.mouseClick(fan, Qt.MouseButton.LeftButton, pos=inside.toPoint())
    assert opened[-1] == fan.selected_id()
