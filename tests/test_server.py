import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from officeflow.server.app import create_app
from tests.conftest import make_pdf, make_xlsx

TOKEN = "test-token"


@pytest.fixture
def client(tmp_path):
    app = create_app(TOKEN, web_dir=tmp_path / "no-ui")
    with TestClient(app, headers={"X-OfficeFlow-Token": TOKEN}) as c:
        yield c
    app.state.db.close()


def wait(client, job):
    for _ in range(500):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["state"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_token_required(tmp_path):
    app = create_app(TOKEN, web_dir=tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/meta").status_code == 401
        assert c.get("/api/meta", headers={"X-OfficeFlow-Token": "wrong"}).status_code == 401
        assert c.get(f"/api/meta?token={TOKEN}").status_code == 200
        assert "has not been built" in c.get("/").text
    app.state.db.close()


def test_meta_and_settings(client, tmp_path):
    meta = client.get("/api/meta").json()
    ids = {op["id"] for op in meta["operations"]}
    assert {"pdf.organize", "excel.merge_files", "word.generate", "word.pdf"} <= ids
    organizer = next(op for op in meta["operations"] if op["id"] == "pdf.organize")
    assert organizer["input_extensions"] == [".pdf"] and organizer["params"][0]["type"] == "multiline"
    saved = client.put("/api/settings", json={"theme": "light", "output_dir": str(tmp_path / "o")}).json()
    assert saved["theme"] == "light" and saved["output_dir"] == str(tmp_path / "o")
    assert client.get("/api/settings").json()["theme"] == "light"


def test_preview_then_run_operation_and_history(client, tmp_path):
    make_pdf(tmp_path / "A" / "x.pdf", ["Ref 2024/01/005"])
    make_pdf(tmp_path / "B" / "y.pdf", ["Ref 2024/01/005"])
    body = {"op": "pdf.organize", "inputs": [str(tmp_path / "A"), str(tmp_path / "B")],
            "output_dir": str(tmp_path / "out"), "params": {}}
    preview = wait(client, client.post("/api/jobs", json={**body, "mode": "preview"}).json())
    assert preview["result"]["status"] == "info" and len(preview["result"]["rows"]) == 2
    assert not (tmp_path / "out").exists()
    done = wait(client, client.post("/api/jobs", json={**body, "mode": "run"}).json())
    assert done["result"]["status"] == "success"
    assert sorted(p.name for p in (tmp_path / "out" / "2024-01-005").iterdir()) == ["x.pdf", "y.pdf"]
    history = client.get("/api/history").json()
    assert history[0]["target_id"] == "pdf.organize" and history[0]["status"] == "success"
    stats = client.get("/api/stats").json()
    assert stats["runs"] == 1 and stats["targets"]["pdf.organize"]["ok"] == 1
    exported = client.post("/api/history/export").json()["path"]
    assert pd.read_excel(exported)["Task"].tolist() == ["PDF Smart Organizer"]


def test_event_stream_reports_progress_until_done(client, tmp_path):
    for i in range(3):
        make_pdf(tmp_path / "in" / f"{i}.pdf", ["x"])
    job = client.post("/api/jobs", json={"mode": "run", "op": "pdf.text", "inputs": [str(tmp_path / "in")],
                                         "output_dir": str(tmp_path / "out")}).json()
    with client.stream("GET", f"/api/jobs/{job['id']}/events") as response:
        events = [line for line in response.iter_lines() if line.startswith("data: ")]
    assert '"state": "done"' in events[-1]


def test_workflow_job_and_saved_workflows(client, tmp_path):
    make_xlsx(tmp_path / "in" / "a.xlsx", [{"Ref": "A"}, {"Ref": " a "}])
    workflow = {"name": "Tidy", "steps": [{"op": "excel.clean"},
                                          {"op": "excel.remove_duplicates", "params": {"columns": "Ref"}}]}
    assert client.put("/api/workflows", json=workflow).status_code == 200
    assert client.get("/api/workflows").json() == [
        {"name": "Tidy", "steps": ["excel.clean", "excel.remove_duplicates"]}]
    job = client.post("/api/jobs", json={"mode": "workflow", "workflow": workflow, "inputs": [str(tmp_path / "in")],
                                         "output_dir": str(tmp_path / "out")}).json()
    state = wait(client, job)
    assert state["result"]["status"] == "success"
    assert [s["status"] for s in state["result"]["steps"]] == ["success", "success"]
    client.delete("/api/workflows/Tidy")
    assert client.get("/api/workflows").json() == []


def test_invalid_requests_return_readable_errors(client):
    bad_chain = {"name": "x", "steps": [{"op": "pdf.text"}, {"op": "pdf.merge"}]}
    response = client.put("/api/workflows", json=bad_chain)
    assert response.status_code == 400 and "cannot use the files produced" in response.json()["detail"]
    assert client.put("/api/workflows", json={"name": "", "steps": [{"op": "pdf.text"}]}).status_code == 400
    assert client.post("/api/jobs", json={"mode": "run", "op": "nope"}).status_code == 404
    failed = wait(client, client.post("/api/jobs", json={"mode": "run", "op": "pdf.merge", "inputs": []}).json())
    assert failed["result"]["status"] == "failed" and "needs at least 2 files" in failed["result"]["summary"]


def test_cancel(client, tmp_path):
    for i in range(40):
        make_pdf(tmp_path / "in" / f"{i}.pdf", ["x" * 50] * 5)
    job = client.post("/api/jobs", json={"mode": "run", "op": "pdf.text", "inputs": [str(tmp_path / "in")],
                                         "output_dir": str(tmp_path / "out")}).json()
    client.post(f"/api/jobs/{job['id']}/cancel")
    state = wait(client, job)
    assert state["result"]["status"] in ("cancelled", "success")


def test_file_browser_scan_and_exists(client, tmp_path):
    tmp_path = tmp_path / "files"
    tmp_path.mkdir()
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "~$lock.pdf").write_text("x")
    listing = client.get("/api/fs/list", params={"path": str(tmp_path), "extensions": ".pdf"}).json()
    assert [(e["name"], e["dir"]) for e in listing["entries"]] == [("sub", True), ("a.pdf", False)]
    assert listing["parent"] == str(tmp_path.parent) and listing["roots"]
    scan = client.post("/api/fs/scan", json={"paths": [str(tmp_path)]}).json()
    assert scan["extensions"] == {".pdf": 1, ".txt": 1}
    exists = client.post("/api/fs/exists", json={"paths": [str(tmp_path / "a.pdf"), str(tmp_path / "zz")]}).json()
    assert [i["exists"] for i in exists["items"]] == [True, False]


def test_pages_are_never_cached_but_build_files_are(tmp_path):
    web = tmp_path / "web"
    (web / "_next" / "static").mkdir(parents=True)
    (web / "index.html").write_text("<html>ui</html>")
    (web / "_next" / "static" / "app.123.js").write_text("x")
    app = create_app(TOKEN, web_dir=web)
    with TestClient(app) as c:
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert c.get("/api/meta", headers={"X-OfficeFlow-Token": TOKEN}).headers["cache-control"] == "no-cache"
        assert "immutable" in c.get("/_next/static/app.123.js").headers["cache-control"]
    app.state.db.close()


def test_interface_errors_are_written_to_the_log(client):
    client.post("/api/client-error", json={"message": "TypeError: x is undefined", "page": "/settings/", "stack": "at y"})
    lines = "\n".join(client.get("/api/logs?level=errors").json()["lines"])
    assert "Interface error on /settings/: TypeError: x is undefined" in lines
