"""Background jobs: operations, previews and workflows run in threads; the
interface follows them through polling or Server-Sent Events."""

from __future__ import annotations

import itertools
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from officeflow.core.operation import Cancelled, OperationContext, OperationError, OperationResult, Preview

MAX_ROWS = 2000
_ids = itertools.count(1)


def result_json(result: OperationResult | Preview, status: str) -> dict[str, Any]:
    rows = [[str(c) for c in row] for row in result.rows[:MAX_ROWS]]
    data: dict[str, Any] = {
        "status": status, "summary": result.summary, "headers": result.headers, "rows": rows,
        "total_rows": len(result.rows), "warnings": result.warnings[:500],
    }
    if isinstance(result, OperationResult):
        data.update(errors=result.errors[:500], outputs=[str(p) for p in result.outputs[:MAX_ROWS]],
                    output_count=len(result.outputs), reports=[str(p) for p in result.reports])
    else:
        data.update(errors=[], outputs=[], output_count=0, reports=[])
    return data


@dataclass
class Job:
    id: str
    kind: str
    output_dir: str
    state: str = "running"                  # running | done | error
    progress: dict[str, Any] = field(default_factory=lambda: {"done": 0, "total": 0, "message": "Starting…"})
    steps: dict[int, str] = field(default_factory=dict)   # workflow step index → running/success/...
    result: dict[str, Any] | None = None
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)
    version: int = 0                        # bumped on every change (for event streams)
    started: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "state": self.state, "progress": self.progress,
                "steps": {str(k): v for k, v in self.steps.items()}, "result": self.result,
                "error": self.error, "output_dir": self.output_dir, "version": self.version,
                "elapsed": round(time.time() - self.started, 1)}


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def busy(self) -> bool:
        return any(job.state == "running" for job in self._jobs.values())

    def start(self, kind: str, output_dir: Path, task: Callable[[OperationContext], dict[str, Any]]) -> Job:
        job = Job(f"j{next(_ids)}", kind, str(output_dir))

        def progress(done: int, total: int, message: str) -> None:
            with self._lock:
                job.progress = {"done": done, "total": total, "message": message}
                match = re.match(r"Step (\d+)/", message)
                if kind == "workflow" and match:
                    current = int(match.group(1)) - 1
                    for index in list(job.steps):
                        if index < current and job.steps[index] == "running":
                            job.steps[index] = "success"
                    job.steps.setdefault(current, "running")
                job.version += 1

        ctx = OperationContext(output_dir, progress, job.cancel)

        def work() -> None:
            try:
                result = task(ctx)
                with self._lock:
                    job.result, job.state = result, "done"
            except Cancelled:
                with self._lock:
                    job.result, job.state = {"status": "cancelled", "summary": "Cancelled.", "headers": [],
                                             "rows": [], "warnings": [], "errors": [], "outputs": [],
                                             "output_count": 0, "reports": [], "total_rows": 0}, "done"
            except OperationError as exc:
                with self._lock:
                    job.error, job.state = str(exc), "error"
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger("officeflow.server").exception("Job %s crashed", job.id)
                with self._lock:
                    job.error, job.state = f"Unexpected error: {exc.__class__.__name__}: {exc}", "error"
            finally:
                with self._lock:
                    job.version += 1

        with self._lock:
            self._jobs[job.id] = job
            # keep memory bounded: forget old finished jobs
            finished = [j for j in self._jobs.values() if j.state != "running"]
            for old in sorted(finished, key=lambda j: j.started)[:-50]:
                self._jobs.pop(old.id, None)
        threading.Thread(target=work, name=f"job-{job.id}", daemon=True).start()
        return job

    def wait(self, job_id: str, timeout: float = 60) -> Job:
        deadline = time.time() + timeout
        job = self._jobs[job_id]
        while job.state == "running" and time.time() < deadline:
            time.sleep(0.02)
        return job
