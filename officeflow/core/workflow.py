"""Reusable workflows: an ordered chain of operations.

Each step receives the *output files* of the previous step as its input, and
writes into its own numbered sub-folder so intermediate results stay
inspectable: ``output/01 Clean data/…``, ``output/02 Remove duplicates/…``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from officeflow.core import registry
from officeflow.core.operation import OperationContext, OperationError, OperationResult
from officeflow.core.runner import RunOutcome, run_operation
from officeflow.services.database import Database
from officeflow.services.files import safe_filename


@dataclass
class Step:
    op_id: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Workflow:
    name: str
    steps: list[Step] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "steps": [{"op": s.op_id, "params": s.params} for s in self.steps]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        return cls(data["name"], [Step(s["op"], dict(s.get("params", {}))) for s in data["steps"]])

    def validate(self) -> None:
        """Fail early (before touching any file) on unknown tools, bad
        parameters, or steps whose files cannot flow into the next one."""
        if not self.steps:
            raise OperationError("The workflow has no steps.")
        for number, step in enumerate(self.steps, 1):
            try:
                op = registry.get(step.op_id)
            except KeyError:
                raise OperationError(f"Step {number}: unknown tool “{step.op_id}”.") from None
            try:
                op.clean_params(step.params)
            except OperationError as exc:
                raise OperationError(f"Step {number} ({op.name}): {exc}") from None
            if number > 1:
                previous = registry.get(self.steps[number - 2].op_id)
                if not set(previous.output_extensions) & set(op.input_extensions):
                    raise OperationError(
                        f"Step {number} ({op.name}) cannot use the files produced by step "
                        f"{number - 1} ({previous.name}): it needs {', '.join(op.input_extensions)} "
                        f"but receives {', '.join(previous.output_extensions)}.")


@dataclass
class WorkflowOutcome:
    status: str
    summary: str
    steps: list[tuple[str, RunOutcome]] = field(default_factory=list)

    @property
    def outputs(self) -> list[Path]:
        return self.steps[-1][1].result.outputs if self.steps else []


def run_workflow(
    workflow: Workflow, inputs: Sequence[Path | str], ctx: OperationContext,
    recursive: bool = True, db: Database | None = None,
) -> WorkflowOutcome:
    started, clock = datetime.now(), time.perf_counter()
    outcome = WorkflowOutcome("success", "")
    try:
        workflow.validate()
    except OperationError as exc:
        outcome.status, outcome.summary = "failed", str(exc)
    else:
        current: Sequence[Path | str] = inputs
        total = len(workflow.steps)
        for index, step in enumerate(workflow.steps):
            op = registry.get(step.op_id)
            label = f"Step {index + 1}/{total} · {op.name}"

            def progress(done: int, count: int, message: str, _i=index, _label=label) -> None:
                fraction = done / count if count else 0
                ctx.progress(int((_i + fraction) * 1000), total * 1000, f"{_label} — {message}")

            step_ctx = ctx.child(f"{index + 1:02d} {safe_filename(op.name)}", progress)
            result = run_operation(op, current, step.params, step_ctx, recursive)
            outcome.steps.append((op.name, result))
            if result.status in ("failed", "cancelled"):
                outcome.status = result.status
                outcome.summary = f"{label} {result.status}: {result.result.summary}"
                break
            if result.status == "warning":
                outcome.status = "warning"
            current = result.result.outputs
            if index + 1 < total and not current:
                outcome.status = "failed"
                outcome.summary = f"{label} produced no files for the next step."
                break
        else:
            outcome.summary = (
                f"Workflow finished: {total} step(s), {len(outcome.outputs)} final file(s)."
            )
    if db is not None:
        db.add_run(
            kind="workflow", target_id=workflow.name, name=workflow.name, started_at=started,
            duration_s=time.perf_counter() - clock, status=outcome.status,
            input_count=outcome.steps[0][1].input_count if outcome.steps else 0,
            output_count=len(outcome.outputs), output_dir=ctx.output_dir, summary=outcome.summary,
            details={"steps": [{"name": n, "status": o.status, "summary": o.result.summary,
                                "errors": o.result.errors[:50], "warnings": o.result.warnings[:50]}
                               for n, o in outcome.steps]},
        )
    return outcome


def as_result(outcome: WorkflowOutcome) -> OperationResult:
    """Flatten a workflow outcome into the table shape the GUI displays."""
    result = OperationResult(outcome.summary, outputs=outcome.outputs,
                             headers=["Step", "Status", "Result"])
    for number, (name, step) in enumerate(outcome.steps, 1):
        result.rows.append([f"{number}. {name}", step.status, step.result.summary])
        result.warnings += step.result.warnings
        result.errors += step.result.errors
    return result
