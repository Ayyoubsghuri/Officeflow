"""AI assistant tests. No real API calls: a fake client stands in for Claude."""

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from officeflow.ai import assistant as ai
from officeflow.ai.plugin_check import check_plugin
from officeflow.ai.privacy import catalog, redact
from officeflow.core import registry
from officeflow.server.app import create_app
from officeflow.services import secrets as keystore
from tests.conftest import make_pdf

GOOD_PLUGIN = '''
from officeflow.core.operation import Operation, OperationResult, Param, ParamType
from officeflow.core.registry import register
from officeflow.engines.pdf.reader import open_pdf
import pandas as pd


@register
class CountPages(Operation):
    id = "pdf.count_pages_test"
    name = "Count pages"
    category = "pdf"
    description = "Count the pages of each PDF."
    input_extensions = (".pdf",)
    output_extensions = (".xlsx",)
    params = (Param("label", "Label", ParamType.TEXT, "Pages"),)

    def run(self, inputs, params, ctx):
        from officeflow.engines.excel.io import write_table
        rows = []
        for i, path in enumerate(inputs):
            ctx.progress(i, len(inputs), path.name)
            with open_pdf(path) as doc:
                rows.append([path.name, doc.page_count])
        out = ctx.out_path("pages.xlsx")
        write_table(pd.DataFrame(rows, columns=["File", params["label"]]), out)
        return OperationResult(f"{len(rows)} PDF(s) counted.", [out])
'''


class FakeClient:
    """Mimics client.beta.messages.parse, returning queued answers."""

    def __init__(self, *answers, stop_reason="end_turn"):
        self.answers = list(answers)
        self.calls = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        answer = self.answers.pop(0)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=answer,
                               content=[{"type": "text", "text": answer.model_dump_json()}],
                               usage=SimpleNamespace(input_tokens=100, output_tokens=50,
                                                     cache_read_input_tokens=0, cache_creation_input_tokens=0))


def workflow_answer(steps, missing=()):
    return ai.WorkflowAnswer(
        name="Sort invoices", explanation="Sorts PDFs by reference.",
        steps=[ai.StepDraft(tool_id=t, settings=[ai.Setting(key=k, value=v) for k, v in s.items()]) for t, s in steps],
        missing_tools=[ai.MissingTool(**m) for m in missing])


# -- privacy -------------------------------------------------------------------------
def test_redaction_hides_paths_and_emails_but_keeps_patterns():
    r = redact(r"Sort C:\Users\ali\My Documents\Factures\ and \\srv\RH\x.xlsx, mail a.b@x.ma; pattern \b\d{4}/\d{2}\b")
    assert r.text == r"Sort <path-1> and <path-2>, mail <email-1>; pattern \b\d{4}/\d{2}\b"
    assert [x["placeholder"] for x in r.replaced] == ["<path-1>", "<path-2>", "<email-1>"]
    again = redact("same C:\\a\\b.pdf and C:\\a\\b.pdf")
    assert again.text == "same <path-1> and <path-1>"


def test_catalog_contains_product_information_only():
    tools = catalog()
    organizer = next(t for t in tools if t["id"] == "pdf.organize")
    assert organizer["reads"] == [".pdf"] and organizer["params"][0]["key"] == "patterns"
    assert set(organizer) == {"id", "name", "category", "description", "reads", "writes", "min_inputs",
                              "max_inputs", "params"}


# -- plugin safety check ---------------------------------------------------------------
def test_plugin_check_accepts_offline_plugin():
    result = check_plugin(GOOD_PLUGIN, registry.builtin_ids())
    assert result.ok, result.errors
    assert result.tools == [{"id": "pdf.count_pages_test", "name": "Count pages", "category": "pdf",
                             "class": "CountPages"}]


@pytest.mark.parametrize("change, message", [
    (("import pandas as pd", "import requests"), "importing “requests” is not allowed"),
    (("import pandas as pd", "from urllib.request import urlopen"), "importing from “urllib.request”"),
    (("import pandas as pd", "import subprocess"), "importing “subprocess”"),
    (("rows = []", "rows = eval('[]')"), "calling “eval” is not allowed"),
    (("rows = []", "rows = ().__class__"), "access to “__class__”"),
    (('id = "pdf.count_pages_test"', 'id = "excel.count"'), "must start with “pdf.”"),
    (('id = "pdf.count_pages_test"', 'id = "pdf.merge"'), "would replace a built-in tool"),
    (('output_extensions = (".xlsx",)', 'output_extensions = ".xlsx"'), "output_extensions must be a tuple"),
])
def test_plugin_check_rejects_unsafe_or_invalid_code(change, message):
    result = check_plugin(GOOD_PLUGIN.replace(*change), registry.builtin_ids())
    assert not result.ok and any(message in e for e in result.errors), result.errors


def test_plugin_check_warns_about_deleting_and_reports_syntax_errors():
    deleting = check_plugin(GOOD_PLUGIN.replace("rows = []", "rows = []\n        path = None\n        "
                                                "inputs[0].unlink()"), registry.builtin_ids())
    assert deleting.ok and "deletes files" in deleting.warnings[0]
    assert "Syntax error" in check_plugin("def broken(:", set()).errors[0]
    assert check_plugin("x = 1", set()).errors == ["No @register tool class found."]


# -- assistant (fake Claude) -------------------------------------------------------------
def test_design_workflow_fixes_problems_and_sends_no_user_data():
    client = FakeClient(
        workflow_answer([("pdf.organise", {})]),                                           # unknown id
        workflow_answer([("pdf.organize", {"patterns": r"\d{4}/\d{2}", "move": "false", "colour": "x"}),
                         ("pdf.search", {"find": "Total"})],
                        missing=[{"name": "OCR", "description": "Read scans", "reads": [".pdf"], "writes": [".pdf"]}]))
    result = ai.Assistant("key", client=client).design_workflow("Sort my PDFs by <path-1> reference")
    assert result["rounds"] == 2 and result["workflow"]["steps"][0]["params"]["move"] is False
    assert [s["op"] for s in result["workflow"]["steps"]] == ["pdf.organize", "pdf.search"]
    assert any("ignored unknown setting “colour”" in n for n in result["notes"])
    assert result["missing_tools"][0]["name"] == "OCR"
    first = client.calls[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert first["betas"] == ["server-side-fallback-2026-07-01"] and first["output_config"] == {"effort": "medium"}
    assert first["messages"] == [{"role": "user", "content": "Sort my PDFs by <path-1> reference"}]
    assert "pdf.organize" in first["system"][0]["text"]
    retry = client.calls[1]["messages"][-1]["content"]
    assert "unknown tool id 'pdf.organise'" in retry


def test_design_workflow_rejects_incompatible_chain_then_accepts_fix():
    client = FakeClient(workflow_answer([("pdf.text", {}), ("pdf.merge", {})]),
                        workflow_answer([("pdf.merge", {}), ("pdf.text", {})]))
    result = ai.Assistant("key", client=client).design_workflow("merge then text")
    assert "cannot use the files produced" in client.calls[1]["messages"][-1]["content"]
    assert [s["op"] for s in result["workflow"]["steps"]] == ["pdf.merge", "pdf.text"]


def test_create_plugin_retries_until_safety_check_passes():
    bad = ai.PluginAnswer(file_name="Count Pages", explanation="x", code=GOOD_PLUGIN.replace("import pandas as pd", "import requests"))
    good = ai.PluginAnswer(file_name="Count Pages", explanation="Counts pages.", code=GOOD_PLUGIN)
    client = FakeClient(bad, good)
    result = ai.Assistant("key", "claude-haiku-5-5", client=client).create_plugin("count pdf pages")
    assert result["file_name"] == "count_pages.py" and result["check"]["ok"]
    assert "importing “requests” is not allowed" in client.calls[1]["messages"][-1]["content"]
    assert "fallbacks" not in client.calls[0] and client.calls[0]["output_config"] == {"effort": "high"}


def test_refusal_and_missing_key_give_readable_errors():
    client = FakeClient(workflow_answer([]), stop_reason="refusal")
    with pytest.raises(ai.AssistantError, match="declined"):
        ai.Assistant("key", client=client).design_workflow("x")
    with pytest.raises(ai.AssistantError, match="API key"):
        ai.Assistant("")


# -- API ---------------------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    app = create_app("t", web_dir=tmp_path / "none")
    with TestClient(app, headers={"X-OfficeFlow-Token": "t"}) as c:
        c.app_ref = app
        yield c
    app.state.db.close()
    for name in list(registry.plugin_tools()):
        registry.unload_plugin(name)


def wait(client, job):
    for _ in range(300):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["state"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_key_is_stored_locally_and_never_returned(client):
    assert client.put("/api/ai/key", json={"key": "short"}).status_code == 400
    status = client.put("/api/ai/key", json={"key": "sk-ant-test-0123456789abcdefWXYZ"}).json()
    assert status["configured"] and status["key_hint"] == "…WXYZ"
    assert "sk-ant" not in json.dumps(status)
    assert keystore.load_api_key() == "sk-ant-test-0123456789abcdefWXYZ"
    assert not client.delete("/api/ai/key").json()["configured"]


def test_ai_job_sends_redacted_text_and_logs_it_locally(client):
    fake = FakeClient(workflow_answer([("pdf.organize", {})]))
    client.app_ref.state.assistant_factory = lambda key, model: ai.Assistant("k", model, client=fake)
    job = client.post("/api/ai/jobs", json={"kind": "workflow", "request": r"Sort D:\Scans\2024 by reference"}).json()
    state = wait(client, job)
    assert state["result"]["workflow"]["steps"][0]["op"] == "pdf.organize"
    assert fake.calls[0]["messages"][0]["content"] == "Sort <path-1> by reference"
    log = client.get("/api/ai/activity").json()[0]
    assert log["sent_request"] == "Sort <path-1> by reference" and log["kind"] == "workflow"
    assert "D:\\Scans" not in json.dumps(log)


def test_install_run_and_remove_ai_plugin(client, tmp_path):
    bad = client.post("/api/plugins", json={"file_name": "x.py", "code": "import socket"})
    assert bad.status_code == 400 and "safety check" in bad.json()["detail"]
    installed = client.post("/api/plugins", json={"file_name": "count_pages.py", "code": GOOD_PLUGIN}).json()
    assert installed["tools"] == ["pdf.count_pages_test"]
    assert any(o["id"] == "pdf.count_pages_test" for o in client.get("/api/meta").json()["operations"])
    assert client.post("/api/plugins", json={"file_name": "count_pages.py", "code": GOOD_PLUGIN}).status_code == 400
    make_pdf(tmp_path / "in" / "a.pdf", ["1", "2", "3"])
    job = client.post("/api/jobs", json={"mode": "run", "op": "pdf.count_pages_test", "inputs": [str(tmp_path / "in")],
                                         "output_dir": str(tmp_path / "out")}).json()
    assert wait(client, job)["result"]["summary"] == "1 PDF(s) counted."
    assert client.get("/api/plugins").json()[0]["tools"] == [{"id": "pdf.count_pages_test", "name": "Count pages"}]
    assert "class CountPages" in client.get("/api/plugins/count_pages.py").json()["code"]
    client.delete("/api/plugins/count_pages.py")
    assert client.get("/api/plugins").json() == []
    assert not any(o["id"] == "pdf.count_pages_test" for o in client.get("/api/meta").json()["operations"])


def test_plugin_that_fails_to_load_is_rolled_back(client):
    broken = GOOD_PLUGIN.replace("from officeflow.engines.pdf.reader import open_pdf",
                                 "from officeflow.engines.pdf.reader import does_not_exist")
    response = client.post("/api/plugins", json={"file_name": "broken.py", "code": broken})
    assert response.status_code == 400 and "could not be loaded" in response.json()["detail"]
    assert client.get("/api/plugins").json() == []
