import threading

import pandas as pd
import pytest

from officeflow.core import registry
from officeflow.core.operation import (
    Operation, OperationContext, OperationError, OperationResult, Param, ParamType,
)
from officeflow.core.runner import run_operation
from officeflow.core.workflow import Step, Workflow, run_workflow
from officeflow.services.database import Database
from tests.conftest import make_pdf, make_xlsx


def test_every_operation_is_well_formed():
    operations = registry.all_operations()
    assert len(operations) >= 19
    for op in operations:
        assert op.id.split(".")[0] == op.category and op.description
        assert op.input_extensions and op.output_extensions
        keys = [p.key for p in op.params]
        assert len(keys) == len(set(keys))
        for p in op.params:
            if p.type is ParamType.CHOICE:
                assert p.default in [c[0] for c in p.choices]


def test_param_coercion():
    number = Param("n", "N", ParamType.INT, 1, minimum=1, maximum=5)
    assert number.coerce("3") == 3 and number.coerce(None) == 1
    for bad in ("x", 9):
        with pytest.raises(OperationError):
            number.coerce(bad)
    assert Param("b", "B", ParamType.BOOL).coerce("true") is True
    with pytest.raises(OperationError, match="required"):
        Param("t", "T", required=True).coerce("  ")


def test_runner_records_history_and_turns_crashes_into_outcomes(tmp_path):
    class Boom(Operation):
        id, name, category, input_extensions = "pdf.boom", "Boom", "pdf", (".pdf",)

        def run(self, inputs, params, ctx):
            raise RuntimeError("kaput")

    db = Database(tmp_path / "h.db")
    pdf = make_pdf(tmp_path / "a.pdf", ["x"])
    outcome = run_operation(Boom(), [pdf], {}, OperationContext(tmp_path / "out"), db=db)
    assert outcome.status == "failed" and "kaput" in outcome.result.summary
    run_operation(registry.get("pdf.text"), [pdf], {}, OperationContext(tmp_path / "out"), db=db)
    statuses = [(r.target_id, r.status, r.input_count, r.output_count) for r in db.list_runs()]
    assert statuses == [("pdf.text", "success", 1, 1), ("pdf.boom", "failed", 1, 0)]


def test_cancellation_and_progress(tmp_path):
    files = [make_pdf(tmp_path / f"{i}.pdf", ["x"]) for i in range(5)]
    cancel = threading.Event()
    seen = []

    def progress(done, total, message):
        seen.append((done, total))
        if done == 2:
            cancel.set()

    ctx = OperationContext(tmp_path / "out", progress, cancel)
    outcome = run_operation(registry.get("pdf.text"), files, {}, ctx)
    assert outcome.status == "cancelled" and seen[-1] == (2, 5)
    assert len(list((tmp_path / "out").glob("*.txt"))) == 2


def test_plugin_loading(tmp_path):
    (tmp_path / "hello.py").write_text(
        "from officeflow.core.operation import Operation, OperationResult\n"
        "from officeflow.core.registry import register\n"
        "@register\n"
        "class Hello(Operation):\n"
        "    id='excel.hello'; name='Hello'; category='excel'; input_extensions=('.xlsx',)\n"
        "    def run(self, inputs, params, ctx):\n"
        "        return OperationResult('hi')\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("raise ValueError('nope')")
    problems = registry.load_plugins(tmp_path)
    assert registry.get("excel.hello").name == "Hello"
    assert len(problems) == 1 and problems[0].startswith("bad.py")
    registry._operations.pop("excel.hello")


def test_workflow_chains_outputs_into_next_step(tmp_path):
    make_xlsx(tmp_path / "in" / "a.xlsx", [{"Ref": " A ", "V": 1}, {"Ref": "a", "V": 2}])
    make_xlsx(tmp_path / "in" / "b.xlsx", [{"ref": "B", "V": 3}])
    workflow = Workflow("Monthly", [
        Step("excel.merge_files", {"add_source": False}),
        Step("excel.clean"),
        Step("excel.remove_duplicates", {"columns": "Ref", "save_removed": False}),
    ])
    again = Workflow.from_dict(workflow.to_dict())
    assert again == workflow
    db = Database(tmp_path / "h.db")
    seen = []
    ctx = OperationContext(tmp_path / "out", lambda d, t, m: seen.append((d, t, m)))
    outcome = run_workflow(again, [tmp_path / "in"], ctx, db=db)
    assert outcome.status == "success", outcome.summary
    assert pd.read_excel(outcome.outputs[0]).to_dict("list") == {"Ref": ["A", "B"], "V": [1, 3]}
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "01 Merge Excel files", "02 Clean and normalize data", "03 Remove duplicates"]
    assert seen[-1][0] == seen[-1][1] and seen[-1][2].startswith("Step 3/3")
    assert db.list_runs()[0].kind == "workflow" and len(db.list_runs()) == 1


def test_workflow_validation_and_incompatible_steps(tmp_path):
    ctx = OperationContext(tmp_path / "out")
    assert "unknown tool" in run_workflow(Workflow("w", [Step("nope")]), [], ctx).summary
    assert "no steps" in run_workflow(Workflow("w"), [], ctx).summary
    bad = Workflow("w", [Step("pdf.pages", {"pages": ""})])
    assert "Step 1 (Extract specific pages): “Pages” is required." == run_workflow(bad, [], ctx).summary
    assert not (tmp_path / "out").exists()
    pdf = make_pdf(tmp_path / "a.pdf", ["x"])
    mismatch = Workflow("w", [Step("pdf.text"), Step("pdf.merge")])
    outcome = run_workflow(mismatch, [pdf], ctx)
    assert outcome.status == "failed" and outcome.summary == (
        "Step 2 (Merge PDFs) cannot use the files produced by step 1 (Extract PDF text): "
        "it needs .pdf but receives .txt.")
    assert not (tmp_path / "out").exists()
    too_few = run_workflow(Workflow("w", [Step("pdf.pages", {"pages": "1"}), Step("pdf.merge")]), [pdf], ctx)
    assert too_few.status == "failed" and "Step 2/2 · Merge PDFs failed" in too_few.summary
