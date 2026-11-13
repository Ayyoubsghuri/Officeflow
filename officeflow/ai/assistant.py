"""AI assistant: designs workflows and writes plugin tools with Claude.

Privacy: requests carry only the tool catalog (product information) and the
user's request text after path/e-mail redaction — never files, file names,
paths, results or history (see ``officeflow.ai.privacy``). Answers are not
executed: workflows open as drafts in the builder, plugins are installed only
after the user reads and approves the code.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from officeflow.ai import privacy
from officeflow.ai.plugin_check import ALLOWED_MODULES, CheckResult, check_plugin
from officeflow.core import registry
from officeflow.core.operation import OperationError
from officeflow.core.workflow import Step, Workflow
from officeflow.services import paths

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5 — best quality (default)",
    "claude-sonnet-5-5": "Claude Sonnet 5.5 — faster, lower cost",
    "claude-haiku-5-5": "Claude Haiku 5.5 — fastest, lowest cost",
}
# Server-side refusal fallback ("default" routing) is available on these models.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_FIX_ROUNDS = 2


# -- structured answers ----------------------------------------------------------
class Setting(BaseModel):
    key: str
    value: str = Field(description="The value as text: true/false for switches, digits for numbers.")


class StepDraft(BaseModel):
    tool_id: str
    settings: list[Setting]


class MissingTool(BaseModel):
    name: str
    description: str
    reads: list[str] = Field(description="File extensions it reads, e.g. .pdf")
    writes: list[str]


class WorkflowAnswer(BaseModel):
    name: str
    explanation: str = Field(description="Short explanation for the user, in the user's language.")
    steps: list[StepDraft]
    missing_tools: list[MissingTool] = Field(description="Tools that would be needed but do not exist.")


class PluginAnswer(BaseModel):
    file_name: str = Field(description="snake_case file name ending in .py")
    explanation: str = Field(description="What the tool does and how to use it, in the user's language.")
    code: str


# -- prompts (static, so they are cached) ---------------------------------------------
WORKFLOW_SYSTEM = """You design workflows for OfficeFlow, an offline desktop app that automates Excel, PDF and Word work.
A workflow is an ordered chain of tools from the catalog below. The user's files go into the first step; every
following step receives the files produced by the step before it.

You never see the user's files and must not ask for them. Text such as <path-1> or <email-1> stands for something
the user removed for privacy: never invent paths or addresses; leave such settings empty and say in the explanation
what the user should fill in.

Rules:
- Use only tool ids from the catalog, and only setting keys listed for that tool. Omit settings that keep their default.
- Each step must read at least one file type that the previous step writes ("reads" / "writes").
- Values are text: "true"/"false" for switches, digits for numbers, one of the listed choices for choice settings.
  Regular expressions use Python syntax; put one pattern per line in multiline settings.
- Keep workflows as short as the task allows. Prefer tools that keep original files untouched (no "move").
- If the task needs something no tool can do, list it in missing_tools (name, description, reads, writes) and build
  the rest of the workflow around it if that is still useful; an empty steps list is acceptable.
- name: a short workflow name. explanation: 2-5 sentences in the user's language: what each step does and anything
  the user must choose before running (input folder, template file, column names).

Tool catalog (JSON):
"""

PLUGIN_SYSTEM = """You write plugin tools for OfficeFlow, an offline desktop app (Python 3.10+) that automates Excel,
PDF and Word work. A plugin is one Python file placed in the user's plugin folder. It runs on the user's computer;
it must work fully offline and never send data anywhere.

You never see the user's files. Text such as <path-1> or <email-1> stands for something the user removed for privacy.

Contract (import exactly from these modules):

    from officeflow.core.operation import (Operation, OperationContext, OperationError, OperationResult,
                                           Param, ParamType, Preview)
    from officeflow.core.registry import register

    @register
    class MyTool(Operation):
        id = "pdf.my_tool"              # "<category>.<snake_name>"; category is excel, pdf, word or cross
        name = "My tool"                # short, shown on cards
        category = "pdf"
        description = "One or two sentences for the user."
        input_extensions = (".pdf",)    # file types collected from the chosen files/folders
        output_extensions = (".xlsx",)  # file types this tool writes (lets workflows chain tools)
        input_label = "PDF files or folders"
        min_inputs = 1                  # max_inputs = None by default
        params = (
            Param("pattern", "Pattern to find", ParamType.TEXT, default="", required=True, help="..."),
            Param("ignore_case", "Ignore case", ParamType.BOOL, True),
            Param("mode", "Mode", ParamType.CHOICE, "a", choices=(("a", "Label A"), ("b", "Label B"))),
            Param("pages", "Pages to read", ParamType.INT, 0, minimum=0, maximum=10000),
        )                               # ParamType: TEXT, MULTILINE, INT, BOOL, CHOICE, FILE (FILE takes extensions=(".docx",))

        def run(self, inputs, params, ctx: OperationContext) -> OperationResult:
            # inputs: list[pathlib.Path] (already expanded from folders, filtered by input_extensions)
            # params: dict of validated values keyed by Param.key
            result = OperationResult("", headers=["File", "Result"])
            for index, path in enumerate(inputs):
                ctx.progress(index, len(inputs), path.name)          # also handles Cancel
                try:
                    out = ctx.out_path(path.stem + ".xlsx")          # never overwrites: adds " (2)"
                    ...
                    result.outputs.append(out)                       # files handed to the next workflow step
                    result.rows.append([path.name, "done"])
                except OperationError as exc:                        # one bad file must not stop the batch
                    result.errors.append(str(exc))
            result.summary = f"{len(result.outputs)} file(s) created."
            return result

        # optional: def preview(self, inputs, params, ctx) -> Preview(summary, headers, rows, warnings)
        # must not write any file.

Helpers you may use:
- officeflow.engines.excel.io: read_table(path, sheet="") -> DataFrame (text kept as text), read_all_sheets(path),
  write_table(frame, path, sheet="Data"), write_workbook(path, {sheet_name: frame}), write_csv(frame, path)
- officeflow.engines.pdf.reader: open_pdf(path) -> pymupdf.Document (raises OperationError for damaged or
  password-protected files), iter_page_texts(path, max_pages=0) -> page texts
- officeflow.engines.word.document: open_docx(path), iter_paragraphs(document), document_text(document)
- officeflow.services.files: safe_filename(text) (valid file name, keeps Arabic)
- officeflow.services.textnorm: normalize_text(text) (Arabic/Unicode normalisation, Arabic digits -> 0-9),
  to_western_digits(text)

Rules:
- Allowed imports only: {allowed}. No networking, no subprocess/os.system, no eval/exec/compile/__import__,
  no dunder attribute access. Use pathlib for paths.
- Never modify or delete the input files; write results only through ctx.out_path(...).
- Raise OperationError("readable message") for problems the user can fix; text in messages is in English.
- Handle Unicode and Arabic text; read text files as UTF-8.
- One file, one or more @register classes, no code that runs at import time other than definitions.
- file_name: snake_case ending in .py. explanation: how to use the tool, in the user's language.
""".replace("{allowed}", ", ".join(sorted(ALLOWED_MODULES)))


class AssistantError(OperationError):
    pass


def _client(api_key: str):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=300)


def _readable(exc: Exception) -> str:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return "The API key was rejected. Check it in Settings → AI assistant."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key is not allowed to use the selected model."
    if isinstance(exc, anthropic.NotFoundError):
        return "The selected model is not available for this API key. Choose another model in Settings."
    if isinstance(exc, anthropic.RateLimitError):
        return "The AI service is busy or the usage limit was reached. Try again in a minute."
    if isinstance(exc, anthropic.BadRequestError):
        return f"The AI service rejected the request: {exc.message}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"The AI service returned an error ({exc.status_code}). Try again later."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Cannot reach the AI service. Check the internet connection."
    return f"AI request failed: {exc}"


class Assistant:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, client: Any = None) -> None:
        if not api_key and client is None:
            raise AssistantError("Add an API key in Settings → AI assistant first.")
        self.model = model if model in MODELS else DEFAULT_MODEL
        self._client = client or _client(api_key)

    # -- transport ---------------------------------------------------------------------
    def _ask(self, system: str, messages: list[dict[str, Any]], answer: type[BaseModel], effort: str):
        options: dict[str, Any] = {}
        if self.model in _FALLBACK_MODELS:
            options.update(betas=[_FALLBACK_BETA], fallbacks="default")
        try:
            response = self._client.beta.messages.parse(
                model=self.model, max_tokens=16000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages, output_format=answer, output_config={"effort": effort}, **options)
        except Exception as exc:  # noqa: BLE001 - mapped to a readable message
            if isinstance(exc, OperationError):
                raise
            log.warning("AI request failed: %s", exc)
            raise AssistantError(_readable(exc)) from None
        if response.stop_reason == "refusal":
            raise AssistantError("The AI declined this request. Rephrase it and try again.")
        if response.stop_reason == "max_tokens":
            raise AssistantError("The answer was too long. Ask for a smaller tool or workflow.")
        parsed = response.parsed_output
        if parsed is None:
            raise AssistantError("The AI returned an answer that could not be read. Try again.")
        return response, parsed

    # -- workflows ---------------------------------------------------------------------
    def design_workflow(self, request: str) -> dict[str, Any]:
        system = WORKFLOW_SYSTEM + json.dumps(privacy.catalog(), ensure_ascii=False)
        messages: list[dict[str, Any]] = [{"role": "user", "content": request}]
        usage = {"input_tokens": 0, "output_tokens": 0}
        for round_ in range(MAX_FIX_ROUNDS + 1):
            response, answer = self._ask(system, messages, WorkflowAnswer, "medium")
            self._count(usage, response)
            workflow, problems, notes = self._build_workflow(answer)
            if not problems:
                return {"kind": "workflow", "name": workflow.name, "explanation": answer.explanation,
                        "workflow": workflow.to_dict(), "notes": notes, "rounds": round_ + 1, "usage": usage,
                        "missing_tools": [m.model_dump() for m in answer.missing_tools]}
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": "OfficeFlow checked this workflow and found problems:\n- "
                          + "\n- ".join(problems) + "\nReturn a corrected answer."}]
        raise AssistantError("The AI could not produce a valid workflow: " + "; ".join(problems))

    @staticmethod
    def _build_workflow(answer: WorkflowAnswer) -> tuple[Workflow, list[str], list[str]]:
        problems, notes, steps = [], [], []
        for number, draft in enumerate(answer.steps, 1):
            try:
                op = registry.get(draft.tool_id)
            except KeyError:
                problems.append(f"Step {number}: unknown tool id {draft.tool_id!r}.")
                continue
            known = {p.key: p for p in op.params}
            params: dict[str, Any] = {}
            for setting in draft.settings:
                param = known.get(setting.key)
                if param is None:
                    notes.append(f"Step {number} ({op.name}): ignored unknown setting “{setting.key}”.")
                    continue
                try:
                    params[param.key] = param.coerce(setting.value)
                except OperationError as exc:
                    if param.type.value == "file":       # a file the user must choose: leave it empty
                        notes.append(f"Step {number} ({op.name}): choose “{param.label}” before running.")
                    else:
                        problems.append(f"Step {number} ({op.name}), setting {param.key}: {exc}")
            steps.append(Step(op.id, params))
        workflow = Workflow(answer.name.strip()[:80] or "AI workflow", steps)
        if steps and not problems:
            try:
                workflow.validate()
            except OperationError as exc:
                message = str(exc)
                if "is required" in message:            # a required value the user must provide
                    notes.append(message)
                else:
                    problems.append(message)
        return workflow, problems, notes

    # -- plugins -------------------------------------------------------------------------------
    def create_plugin(self, request: str) -> dict[str, Any]:
        builtin = registry.builtin_ids()
        system = PLUGIN_SYSTEM + "\nExisting tool ids (do not reuse): " + ", ".join(sorted(builtin))
        messages: list[dict[str, Any]] = [{"role": "user", "content": request}]
        usage = {"input_tokens": 0, "output_tokens": 0}
        check = CheckResult(ok=False)
        for round_ in range(MAX_FIX_ROUNDS + 1):
            response, answer = self._ask(system, messages, PluginAnswer, "high")
            self._count(usage, response)
            check = check_plugin(answer.code, builtin)
            if check.ok:
                name = answer.file_name.strip().lower().replace(" ", "_")
                name = "".join(c for c in name if c.isalnum() or c in "_.") or "ai_tool.py"
                if not name.endswith(".py"):
                    name += ".py"
                return {"kind": "plugin", "file_name": name, "explanation": answer.explanation,
                        "code": answer.code, "check": check.__dict__, "rounds": round_ + 1, "usage": usage}
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": "The OfficeFlow safety check rejected the code:\n- "
                          + "\n- ".join(check.errors) + "\nReturn corrected code that follows every rule."}]
        raise AssistantError("The AI could not produce a plugin that passes the safety check: "
                             + "; ".join(check.errors))

    @staticmethod
    def _count(usage: dict[str, int], response) -> None:
        tokens = getattr(response, "usage", None)
        if tokens is not None:
            usage["input_tokens"] += (getattr(tokens, "input_tokens", 0) or 0) + (
                getattr(tokens, "cache_read_input_tokens", 0) or 0) + (getattr(tokens, "cache_creation_input_tokens", 0) or 0)
            usage["output_tokens"] += getattr(tokens, "output_tokens", 0) or 0


# -- local audit log -------------------------------------------------------------------------
def log_file():
    return paths.app_home() / "ai_activity.jsonl"


def record(kind: str, model: str, sent: str, outcome: str, usage: dict[str, int] | None = None) -> None:
    """Keep, on this computer, exactly what was sent to the AI service."""
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "model": model,
             "sent_request": sent, "also_sent": "the OfficeFlow tool catalog / plugin instructions (no user data)",
             "outcome": outcome, "usage": usage or {}}
    with open(log_file(), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def activity(limit: int = 100) -> list[dict[str, Any]]:
    try:
        lines = log_file().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    entries = []
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries

