"""Runs operations on behalf of any front end.

The runner is the only place that expands folders, validates parameters,
converts crashes into readable errors and writes the processing history.
It has no GUI dependency; the GUI simply calls it from a worker thread.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from officeflow.core.operation import (
    Cancelled,
    Operation,
    OperationContext,
    OperationError,
    OperationResult,
    Preview,
)
from officeflow.services.database import Database
from officeflow.services.files import collect_files

log = logging.getLogger(__name__)


@dataclass
class RunOutcome:
    status: str  # 'success' | 'warning' | 'failed' | 'cancelled'
    result: OperationResult
    input_count: int = 0
    duration_s: float = 0.0


def prepare(
    op: Operation, raw_inputs: Sequence[Path | str], raw_params: Mapping[str, Any] | None,
    recursive: bool = True, output_dir: Path | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    params = op.clean_params(raw_params)
    inputs = collect_files(raw_inputs, op.input_extensions, recursive)
    if output_dir is not None:
        # Results of an earlier run must never be picked up as new inputs
        # when the output folder sits inside one of the source folders.
        root = output_dir.resolve()
        inputs = [p for p in inputs if root not in p.resolve().parents]
    op.check_inputs(inputs)
    return inputs, params


def preview_operation(
    op: Operation, raw_inputs: Sequence[Path | str], raw_params: Mapping[str, Any] | None,
    ctx: OperationContext, recursive: bool = True,
) -> Preview:
    inputs, params = prepare(op, raw_inputs, raw_params, recursive, ctx.output_dir)
    return op.preview(inputs, params, ctx)


def status_of(result: OperationResult) -> str:
    return "warning" if (result.warnings or result.errors) else "success"


def run_operation(
    op: Operation, raw_inputs: Sequence[Path | str], raw_params: Mapping[str, Any] | None,
    ctx: OperationContext, recursive: bool = True, db: Database | None = None,
) -> RunOutcome:
    """Execute ``op``. Never raises: failures are returned as an outcome."""
    started = datetime.now()
    clock = time.perf_counter()
    inputs: list[Path] = []
    try:
        inputs, params = prepare(op, raw_inputs, raw_params, recursive, ctx.output_dir)
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        log.info("Start %s on %d file(s) -> %s", op.id, len(inputs), ctx.output_dir)
        result = op.run(inputs, params, ctx)
        status = status_of(result)
    except Cancelled:
        status, result = "cancelled", OperationResult("Cancelled. Files already written were kept.")
    except OperationError as exc:
        status, result = "failed", OperationResult(str(exc), errors=[str(exc)])
    except Exception as exc:  # noqa: BLE001 - last line of defence for the UI
        log.exception("Operation %s crashed", op.id)
        message = f"Unexpected error: {exc.__class__.__name__}: {exc}"
        status, result = "failed", OperationResult(message, errors=[message])
    outcome = RunOutcome(status, result, len(inputs), time.perf_counter() - clock)
    for line in result.errors:
        log.error("%s: %s", op.id, line)
    for line in result.warnings:
        log.warning("%s: %s", op.id, line)
    log.info("End %s: %s (%s)", op.id, status, result.summary)
    if db is not None:
        db.add_run(
            kind="operation", target_id=op.id, name=op.name, started_at=started,
            duration_s=outcome.duration_s, status=status, input_count=len(inputs),
            output_count=len(result.outputs), output_dir=ctx.output_dir, summary=result.summary,
            details={"params": dict(raw_params or {}), "warnings": result.warnings[:200],
                     "errors": result.errors[:200]},
        )
    return outcome
