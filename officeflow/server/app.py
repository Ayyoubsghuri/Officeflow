"""FastAPI application: everything the web interface needs, nothing more.

The server only listens on 127.0.0.1 and every ``/api`` call must carry the
per-launch token (header ``X-OfficeFlow-Token`` or ``?token=`` for event
streams), so other web pages open in the user's browser cannot use it.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import string
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import officeflow
from officeflow.core import registry
from officeflow.core.operation import OperationError, ParamType
from officeflow.core.runner import preview_operation, run_operation
from officeflow.core.workflow import Step, Workflow, as_result, run_workflow
from officeflow.engines.excel import io as excel_io
from officeflow.engines.word import convert
from officeflow.server.jobs import JobManager, result_json
from officeflow.services import paths
from officeflow.services.database import Database
from officeflow.ai import assistant as ai
from officeflow.ai import privacy
from officeflow.ai.plugin_check import check_plugin
from officeflow.services import secrets as keystore
from officeflow.services.files import safe_filename, unique_path
from officeflow.services.logsetup import setup_logging
from officeflow.services.settings import Settings

log = logging.getLogger("officeflow.server")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# -- request bodies ------------------------------------------------------------
class SettingsBody(BaseModel):
    theme: str | None = None
    output_dir: str | None = None
    include_subfolders: bool | None = None
    last_input_dir: str | None = None
    ai_model: str | None = None
    ai_redact: bool | None = None
    ai_provider: str | None = None
    ai_openai_model: str | None = None
    ai_openrouter_model: str | None = None
    ai_nvidia_model: str | None = None


class KeyBody(BaseModel):
    key: str
    provider: str = "anthropic"


class AiRequestBody(BaseModel):
    kind: str            # workflow | plugin
    request: str


class PluginBody(BaseModel):
    file_name: str
    code: str
    replace: bool = False


class StepBody(BaseModel):
    op: str
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowBody(BaseModel):
    name: str = ""
    steps: list[StepBody] = Field(default_factory=list)
    folder: str | None = None


class FolderBody(BaseModel):
    folder: str = ""


class RenameFolderBody(BaseModel):
    old: str
    new: str


class JobBody(BaseModel):
    mode: str                                  # preview | run | workflow
    op: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    workflow: WorkflowBody | None = None
    inputs: list[str] = Field(default_factory=list)
    output_dir: str = ""
    recursive: bool = True
    keep_intermediate: bool = False


class PathBody(BaseModel):
    path: str


class ClientErrorBody(BaseModel):
    message: str
    page: str = ""
    stack: str = ""


class ScanBody(BaseModel):
    paths: list[str]


# -- helpers -----------------------------------------------------------------------
def describe_operation(op) -> dict[str, Any]:
    return {
        "id": op.id, "name": op.name, "category": op.category, "description": op.description,
        "input_label": op.input_label, "input_extensions": list(op.input_extensions),
        "output_extensions": list(op.output_extensions), "min_inputs": op.min_inputs,
        "max_inputs": op.max_inputs,
        "params": [{"key": p.key, "label": p.label, "type": p.type.value, "default": p.default, "help": p.help,
                    "choices": [list(c) for c in p.choices], "required": p.required, "minimum": p.minimum,
                    "maximum": p.maximum, "placeholder": p.placeholder, "extensions": list(p.extensions)}
                   for p in op.params],
    }


def workflow_from(body: WorkflowBody) -> Workflow:
    return Workflow(body.name.strip(), [Step(s.op, dict(s.params)) for s in body.steps])


def roots() -> list[dict[str, str]]:
    home = Path.home()
    places = [("Home", home), ("Desktop", home / "Desktop"), ("Documents", home / "Documents"),
              ("Downloads", home / "Downloads")]
    found = [{"name": n, "path": str(p)} for n, p in places if p.is_dir()]
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                found.append({"name": f"{letter}:", "path": str(drive)})
    else:
        found.append({"name": "Computer", "path": "/"})
    return found


def open_in_explorer(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_MISSING_UI = """<!doctype html><meta charset="utf-8"><title>OfficeFlow</title>
<body style="font-family:sans-serif;background:#0a0b0c;color:#f4f6f8;padding:48px">
<h1>OfficeFlow</h1><p>The interface has not been built yet. Run:</p>
<pre style="background:#151718;padding:16px;border-radius:12px">cd frontend
npm install
npm run build</pre><p>then start OfficeFlow again.</p></body>"""


# -- application -------------------------------------------------------------------
def create_app(token: str | None = None, dev_origins: list[str] | None = None,
               web_dir: Path | None = None) -> FastAPI:
    token = token or secrets.token_urlsafe(24)
    setup_logging()
    registry.load_builtin()
    plugin_problems = registry.load_plugins(paths.plugins_dir())
    for problem in plugin_problems:
        log.error("Plugin not loaded: %s", problem)

    app = FastAPI(title="OfficeFlow", version=officeflow.__version__, docs_url=None, redoc_url=None)
    app.state.token = token
    app.state.db = Database()
    app.state.settings = Settings.load()
    app.state.jobs = JobManager()
    app.state.window = None          # set by the desktop launcher (pywebview window)

    if dev_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(CORSMiddleware, allow_origins=dev_origins, allow_methods=["*"], allow_headers=["*"])

    def check(request: Request) -> None:
        supplied = request.headers.get("x-officeflow-token") or request.query_params.get("token")
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(401, "Missing or invalid token.")

    api = Depends(check)

    @app.exception_handler(OperationError)
    async def operation_error(_request, exc: OperationError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # -- meta, settings ------------------------------------------------------
    @app.get("/api/meta", dependencies=[api])
    def meta() -> dict[str, Any]:
        return {
            "version": officeflow.__version__, "platform": sys.platform, "categories": registry.CATEGORIES,
            "operations": [describe_operation(op) for op in registry.all_operations()],
            "pdf_converter": convert.converter_name(), "plugin_problems": plugin_problems,
            "home": str(paths.app_home()), "desktop": app.state.window is not None,
        }

    @app.get("/api/settings", dependencies=[api])
    def get_settings() -> dict[str, Any]:
        s: Settings = app.state.settings
        return {"theme": s.theme, "output_dir": str(s.resolved_output_dir()),
                "include_subfolders": s.include_subfolders, "last_input_dir": s.last_input_dir,
                "ai_model": s.ai_model, "ai_redact": s.ai_redact, "ai_provider": s.ai_provider,
                "ai_openai_model": s.ai_openai_model, "ai_openrouter_model": s.ai_openrouter_model,
                "ai_nvidia_model": s.ai_nvidia_model}

    @app.put("/api/settings", dependencies=[api])
    def put_settings(body: SettingsBody) -> dict[str, Any]:
        s: Settings = app.state.settings
        for key, value in body.model_dump(exclude_none=True).items():
            if key == "ai_model" and value not in ai.MODELS:
                raise OperationError(f"Unknown model {value!r}.")
            if key == "ai_provider" and value not in ai.PROVIDERS:
                raise OperationError(f"Unknown AI provider {value!r}.")
            if key in ("ai_openai_model", "ai_openrouter_model", "ai_nvidia_model"):
                value = value.strip()
                if not value or len(value) > 120 or any(c.isspace() for c in value):
                    raise OperationError("Enter a model name, for example gpt-5 or openai/gpt-5.")
            setattr(s, key, value)
        s.save()
        return get_settings()

    # -- history, stats, logs ------------------------------------------------
    @app.get("/api/stats", dependencies=[api])
    def stats() -> dict[str, Any]:
        db: Database = app.state.db
        return {**db.stats(), "targets": db.target_stats()}

    @app.get("/api/history", dependencies=[api])
    def history(limit: int = 300) -> list[dict[str, Any]]:
        return [r.__dict__ for r in app.state.db.list_runs(min(limit, 2000))]

    @app.delete("/api/history", dependencies=[api])
    def clear_history() -> dict[str, bool]:
        app.state.db.clear_runs()
        return {"ok": True}

    @app.post("/api/history/export", dependencies=[api])
    def export_history() -> dict[str, str]:
        runs = app.state.db.list_runs(100_000)
        frame = pd.DataFrame([{
            "Started": r.started_at, "Task": r.name, "Kind": r.kind, "Status": r.status,
            "Files in": r.input_count, "Files out": r.output_count, "Seconds": r.duration_s,
            "Output folder": r.output_dir, "Result": r.summary} for r in runs])
        folder = app.state.settings.resolved_output_dir()
        folder.mkdir(parents=True, exist_ok=True)
        out = unique_path(folder / f"OfficeFlow history {datetime.now():%Y-%m-%d}.xlsx")
        excel_io.write_table(frame, out, "History")
        return {"path": str(out)}

    @app.get("/api/logs", dependencies=[api])
    def logs(level: str = "all") -> dict[str, Any]:
        wanted = {"warnings": ("WARNING", "ERROR", "CRITICAL"), "errors": ("ERROR", "CRITICAL")}.get(level, ())
        lines: deque[str] = deque(maxlen=1500)
        keep = True
        try:
            with open(paths.log_file(), encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line[:4].isdigit():
                        keep = not wanted or any(f"  {w} " in line[:40] for w in wanted)
                    if keep:
                        lines.append(line.rstrip("\n"))
        except FileNotFoundError:
            pass
        return {"lines": list(lines), "file": str(paths.log_file())}

    # -- workflows -----------------------------------------------------------
    @app.get("/api/workflows", dependencies=[api])
    def list_workflows() -> list[dict[str, Any]]:
        return [{"name": e["name"], "folder": e["folder"], "steps": [s["op"] for s in e["definition"]["steps"]]}
                for e in sorted(app.state.db.workflow_entries(), key=lambda e: e["name"])]

    @app.get("/api/workflows/{name}", dependencies=[api])
    def get_workflow(name: str) -> dict[str, Any]:
        data = app.state.db.load_workflow(name)
        if data is None:
            raise HTTPException(404, f"No workflow named “{name}”.")
        folder = next((e["folder"] for e in app.state.db.workflow_entries() if e["name"] == name), "")
        return {**data, "folder": folder}

    @app.put("/api/workflows", dependencies=[api])
    def save_workflow(body: WorkflowBody) -> dict[str, Any]:
        workflow = workflow_from(body)
        if not workflow.name:
            raise OperationError("Give the workflow a name before saving it.")
        workflow.validate()
        folder = None if body.folder is None else clean_folder(body.folder)
        app.state.db.save_workflow(workflow.name, workflow.to_dict(), folder)
        return workflow.to_dict()

    def clean_folder(folder: str) -> str:
        parts = [safe_filename(p).strip() for p in folder.replace("\\", "/").split("/") if p.strip()]
        return "/".join(p for p in parts if p and p != "_")[:200]

    @app.post("/api/workflows/{name}/move", dependencies=[api])
    def move_workflow(name: str, body: FolderBody) -> dict[str, str]:
        if app.state.db.load_workflow(name) is None:
            raise HTTPException(404, f"No workflow named “{name}”.")
        folder = clean_folder(body.folder)
        app.state.db.move_workflow(name, folder)
        return {"name": name, "folder": folder}

    @app.post("/api/folders/rename", dependencies=[api])
    def rename_folder(body: RenameFolderBody) -> dict[str, str]:
        new = clean_folder(body.new)
        if not new:
            raise OperationError("Give the folder a name.")
        app.state.db.rename_folder(clean_folder(body.old), new)
        return {"folder": new}

    @app.get("/api/library", dependencies=[api])
    def library() -> dict[str, Any]:
        """Every workflow that can be reused: saved ones (with their folder), workflows that
        were run without being saved, and workflows proposed by the AI assistant."""
        db: Database = app.state.db
        stats = db.target_stats()
        saved = []
        names = set()
        for entry in db.workflow_entries():
            names.add(entry["name"])
            stat = stats.get(entry["name"], {})
            saved.append({"kind": "saved", "key": f"saved:{entry['name']}", "name": entry["name"],
                          "folder": entry["folder"], "updated_at": entry["updated_at"],
                          "steps": [step["op"] for step in entry["definition"].get("steps", [])],
                          "runs": stat.get("runs", 0), "ok": stat.get("ok", 0),
                          "last_run": stat.get("started_at", ""), "last_status": stat.get("status", ""),
                          "last_summary": stat.get("summary", "")})
        recent, seen = [], set()
        for run in db.list_runs(2000):
            definition = run.details.get("workflow") if run.kind == "workflow" else None
            if not definition or run.name in names:
                continue
            key = json.dumps(definition, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            recent.append({"kind": "run", "key": f"run:{run.id}", "name": run.name, "folder": "",
                           "steps": [step["op"] for step in definition.get("steps", [])], "definition": definition,
                           "runs": 1, "ok": int(run.status in ("success", "warning")), "last_run": run.started_at,
                           "last_status": run.status, "last_summary": run.summary})
            if len(recent) >= 30:
                break
        proposals = []
        for entry in ai.activity(200):
            answer = entry.get("answer") or {}
            workflow = answer.get("workflow")
            if not workflow or not workflow.get("steps") or workflow.get("name") in names:
                continue
            key = json.dumps(workflow, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            proposals.append({"kind": "ai", "key": f"ai:{entry['time']}", "name": workflow.get("name") or "AI workflow",
                              "folder": "", "steps": [step["op"] for step in workflow["steps"]], "definition": workflow,
                              "runs": 0, "ok": 0, "last_run": "", "last_status": "", "last_summary": answer.get("explanation", ""),
                              "proposed_at": entry["time"]})
        return {"saved": saved, "recent": recent, "ai": proposals,
                "folders": sorted({e["folder"] for e in saved if e["folder"]})}

    @app.delete("/api/workflows/{name}", dependencies=[api])
    def delete_workflow(name: str) -> dict[str, bool]:
        app.state.db.delete_workflow(name)
        return {"ok": True}

    # -- jobs ------------------------------------------------------------------
    @app.post("/api/jobs", dependencies=[api])
    def start_job(body: JobBody) -> dict[str, Any]:
        settings: Settings = app.state.settings
        output_dir = Path(body.output_dir) if body.output_dir.strip() else settings.resolved_output_dir()
        inputs = [Path(p) for p in body.inputs]
        db: Database = app.state.db
        if body.mode in ("preview", "run"):
            try:
                op = registry.get(body.op)
            except KeyError:
                raise HTTPException(404, f"Unknown tool {body.op!r}") from None
            if body.mode == "preview":
                def task(ctx):
                    return result_json(preview_operation(op, inputs, body.params, ctx, body.recursive), "info")
            else:
                def task(ctx):
                    outcome = run_operation(op, inputs, body.params, ctx, body.recursive, db)
                    return result_json(outcome.result, outcome.status)
        elif body.mode == "workflow" and body.workflow is not None:
            workflow = workflow_from(body.workflow)
            workflow.name = workflow.name or "Unsaved workflow"
            workflow.validate()

            def task(ctx):
                outcome = run_workflow(workflow, inputs, ctx, body.recursive, db, body.keep_intermediate)
                data = result_json(as_result(outcome), outcome.status)
                data["result_dir"] = str(outcome.result_dir) if outcome.result_dir and outcome.result_dir.is_dir() else ""
                data["steps"] = [{"name": n, "status": o.status, "summary": o.result.summary,
                                  "outputs": len(o.result.outputs)} for n, o in outcome.steps]
                return data
        else:
            raise HTTPException(400, "Unknown job type.")
        job = app.state.jobs.start("workflow" if body.mode == "workflow" else body.mode, output_dir, task)
        return job.snapshot()

    @app.get("/api/jobs/{job_id}", dependencies=[api])
    def job_state(job_id: str) -> dict[str, Any]:
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")
        return job.snapshot()

    @app.post("/api/jobs/{job_id}/cancel", dependencies=[api])
    def cancel_job(job_id: str) -> dict[str, Any]:
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")
        job.cancel.set()
        return job.snapshot()

    @app.get("/api/jobs/{job_id}/events", dependencies=[api])
    def job_events(job_id: str) -> StreamingResponse:
        job = app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")

        def stream():
            seen = -1
            last_beat = time.time()
            while True:
                if job.version != seen:
                    seen = job.version
                    yield f"data: {json.dumps(job.snapshot(), ensure_ascii=False)}\n\n"
                    if job.state != "running":
                        return
                elif time.time() - last_beat > 10:
                    yield ": keep-alive\n\n"
                    last_beat = time.time()
                time.sleep(0.1)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # -- files ---------------------------------------------------------------------
    @app.get("/api/fs/list", dependencies=[api])
    def list_folder(path: str = "", extensions: str = "") -> dict[str, Any]:
        folder = Path(path) if path else Path(app.state.settings.last_input_dir or Path.home())
        if not folder.is_dir():
            folder = Path.home()
        wanted = {e.strip().lower() for e in extensions.split(",") if e.strip()}
        entries = []
        try:
            children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError as exc:
            raise OperationError(f"Cannot open {folder}: {exc.strerror or exc}") from None
        for child in children:
            if child.name.startswith((".", "~$")):
                continue
            try:
                is_dir = child.is_dir()
                if not is_dir and wanted and child.suffix.lower() not in wanted:
                    continue
                entries.append({"name": child.name, "path": str(child), "dir": is_dir,
                                "size": 0 if is_dir else child.stat().st_size, "ext": child.suffix.lower()})
            except OSError:
                continue
        parent = folder.parent if folder.parent != folder else None
        return {"path": str(folder), "parent": str(parent) if parent else None, "entries": entries[:5000],
                "roots": roots()}

    @app.post("/api/fs/scan", dependencies=[api])
    def scan(body: ScanBody) -> dict[str, Any]:
        """Which file types the selected inputs contain (bounded walk)."""
        counts: dict[str, int] = {}
        files = 0
        for raw in body.paths:
            path = Path(raw)
            walker = path.rglob("*") if path.is_dir() else [path]
            for item in walker:
                if files >= 20_000:
                    break
                if item.is_file() and not item.name.startswith(("~$", ".")):
                    files += 1
                    counts[item.suffix.lower()] = counts.get(item.suffix.lower(), 0) + 1
        return {"files": files, "extensions": counts}

    @app.post("/api/fs/exists", dependencies=[api])
    def exists(body: ScanBody) -> dict[str, Any]:
        return {"items": [{"path": p, "exists": Path(p).exists(), "dir": Path(p).is_dir()} for p in body.paths]}

    @app.post("/api/open", dependencies=[api])
    def open_path(body: PathBody) -> dict[str, bool]:
        path = Path(body.path)
        if not path.exists():
            raise OperationError(f"Not found: {path}")
        open_in_explorer(path)
        return {"ok": True}

    @app.post("/api/client-error", dependencies=[api])
    def client_error(body: ClientErrorBody) -> dict[str, bool]:
        """Interface errors are written to the log so they can be found in Logs."""
        log.error("Interface error on %s: %s\n%s", body.page[:200], body.message[:2000], body.stack[:4000])
        return {"ok": True}

    # -- AI assistant ----------------------------------------------------------------
    app.state.assistant_factory = lambda provider, key, model: ai.Assistant(key, model, provider=provider)

    def model_of(s: Settings, provider: str) -> str:
        return {"anthropic": s.ai_model, "openai": s.ai_openai_model, "openrouter": s.ai_openrouter_model,
                "nvidia": s.ai_nvidia_model}.get(provider, "")

    def active_model(s: Settings) -> str:
        return model_of(s, s.ai_provider)

    def sdk_ready(provider: str) -> bool:
        try:
            __import__("anthropic" if provider == "anthropic" else "openai")
            return True
        except ImportError:
            return False

    @app.get("/api/ai/status", dependencies=[api])
    def ai_status() -> dict[str, Any]:
        s: Settings = app.state.settings
        providers = {name: {"label": label, "configured": bool(keystore.load_api_key(name)),
                            "key_hint": keystore.key_hint(name), "sdk": sdk_ready(name), "model": model_of(s, name),
                            "default_model": ai.DEFAULT_MODELS[name]}
                     for name, label in ai.PROVIDERS.items()}
        current = providers[s.ai_provider]
        return {"provider": s.ai_provider, "provider_label": current["label"], "configured": current["configured"],
                "key_hint": current["key_hint"], "sdk": current["sdk"], "model": active_model(s),
                "models": ai.MODELS, "openai_model": s.ai_openai_model, "providers": providers, "redact": s.ai_redact}

    def check_provider(name: str) -> str:
        if name not in ai.PROVIDERS:
            raise OperationError(f"Unknown AI provider {name!r}.")
        return name

    @app.put("/api/ai/key", dependencies=[api])
    def save_key(body: KeyBody) -> dict[str, Any]:
        key = body.key.strip()
        if len(key) < 20 or any(c.isspace() for c in key):
            raise OperationError("That does not look like an API key.")
        keystore.save_api_key(key, check_provider(body.provider))
        return ai_status()

    @app.delete("/api/ai/key", dependencies=[api])
    def delete_key(provider: str = "anthropic") -> dict[str, Any]:
        keystore.delete_api_key(check_provider(provider))
        return ai_status()

    @app.get("/api/ai/models", dependencies=[api])
    def ai_models(provider: str = "openai") -> dict[str, Any]:
        """Models the provider offers to this key (only the model list is requested)."""
        if check_provider(provider) == "anthropic":
            return {"models": list(ai.MODELS)}
        key = keystore.load_api_key(provider)
        if not key:
            raise OperationError(f"Add an {ai.PROVIDERS[provider]} API key first.")
        return {"models": app.state.list_models(provider, key)}

    app.state.list_models = ai.list_provider_models

    @app.post("/api/ai/preview", dependencies=[api])
    def ai_preview(body: AiRequestBody) -> dict[str, Any]:
        """Exactly what would be sent — nothing is sent by this call."""
        redaction = privacy.redact(body.request) if app.state.settings.ai_redact else privacy.Redaction(body.request)
        s: Settings = app.state.settings
        return {"sent": redaction.text, "replaced": redaction.replaced, "catalog_tools": len(privacy.catalog()),
                "model": active_model(s), "provider": s.ai_provider,
                "provider_label": ai.PROVIDERS[s.ai_provider]}

    @app.post("/api/ai/jobs", dependencies=[api])
    def ai_job(body: AiRequestBody) -> dict[str, Any]:
        if body.kind not in ("workflow", "plugin"):
            raise HTTPException(400, "Unknown request type.")
        if not body.request.strip():
            raise OperationError("Describe what you want first.")
        settings: Settings = app.state.settings
        text = privacy.redact(body.request).text if settings.ai_redact else body.request
        provider = settings.ai_provider
        assistant = app.state.assistant_factory(provider, keystore.load_api_key(provider), active_model(settings))

        def task(ctx):
            ctx.progress(0, 0, "Asking the AI…")
            try:
                if body.kind == "workflow":
                    answer = assistant.design_workflow(text)
                    outcome = f"workflow “{answer['name']}” with {len(answer['workflow']['steps'])} step(s)"
                else:
                    answer = assistant.create_plugin(text)
                    outcome = f"plugin {answer['file_name']}"
            except OperationError as exc:
                ai.record(body.kind, f"{provider}/{assistant.model}", text, f"failed: {exc}")
                raise
            ai.record(body.kind, f"{provider}/{assistant.model}", text, outcome, answer.get("usage"), answer)
            answer["sent"] = text
            return answer

        return app.state.jobs.start("ai", settings.resolved_output_dir(), task).snapshot()

    @app.get("/api/ai/activity", dependencies=[api])
    def ai_activity() -> list[dict[str, Any]]:
        return ai.activity()

    # -- plugins -------------------------------------------------------------------
    def plugin_path(name: str) -> Path:
        clean = safe_filename(Path(name).name)
        if not clean.endswith(".py") or clean.startswith("."):
            raise OperationError("A plugin file name must end in .py.")
        return paths.plugins_dir() / clean

    @app.get("/api/plugins", dependencies=[api])
    def list_plugins() -> list[dict[str, Any]]:
        loaded = registry.plugin_tools()
        items = []
        for file in sorted(paths.plugins_dir().glob("*.py")):
            ids = loaded.get(file.name, [])
            items.append({"file": file.name, "tools": [{"id": i, "name": registry.get(i).name} for i in ids],
                          "loaded": bool(ids), "size": file.stat().st_size})
        return items

    @app.get("/api/plugins/{name}", dependencies=[api])
    def read_plugin(name: str) -> dict[str, str]:
        path = plugin_path(name)
        if not path.exists():
            raise HTTPException(404, "No such plugin.")
        return {"file": path.name, "code": path.read_text(encoding="utf-8")}

    @app.post("/api/plugins/check", dependencies=[api])
    def check_code(body: PluginBody) -> dict[str, Any]:
        return check_plugin(body.code, registry.builtin_ids()).__dict__

    @app.post("/api/plugins", dependencies=[api])
    def install_plugin(body: PluginBody) -> dict[str, Any]:
        """Install code the user has read and approved (checked again here)."""
        result = check_plugin(body.code, registry.builtin_ids())
        if not result.ok:
            raise OperationError("The plugin failed the safety check: " + "; ".join(result.errors))
        path = plugin_path(body.file_name)
        if path.exists() and not body.replace:
            raise OperationError(f"A plugin named {path.name} already exists.")
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text(body.code, encoding="utf-8")
        try:
            ids = registry.load_plugin(path)
        except Exception as exc:  # noqa: BLE001 - report and roll back
            if previous is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(previous, encoding="utf-8")
                registry.load_plugin(path)
            raise OperationError(f"The plugin could not be loaded: {exc.__class__.__name__}: {exc}") from None
        log.info("Plugin %s installed with tools %s", path.name, ids)
        return {"file": path.name, "tools": ids}

    @app.delete("/api/plugins/{name}", dependencies=[api])
    def remove_plugin(name: str) -> dict[str, bool]:
        path = plugin_path(name)
        registry.unload_plugin(path.name)
        path.unlink(missing_ok=True)
        log.info("Plugin %s removed", path.name)
        return {"ok": True}

    # -- interface -----------------------------------------------------------
    @app.middleware("http")
    async def cache_policy(request: Request, call_next):
        """Pages must always be re-checked: after an update a cached page would point to
        script files that no longer exist and render blank. Hashed build files never change."""
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/_next/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    web = web_dir or WEB_DIR
    if (web / "index.html").exists():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def missing_ui() -> str:
            return _MISSING_UI

    return app
