"""SQLite persistence: processing history and saved workflows."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from officeflow.services import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- 'operation' | 'workflow'
    target_id TEXT NOT NULL,
    name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_s REAL NOT NULL,
    status TEXT NOT NULL,            -- 'success' | 'warning' | 'failed' | 'cancelled'
    input_count INTEGER NOT NULL,
    output_count INTEGER NOT NULL,
    output_dir TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT NOT NULL            -- JSON: params, warnings, errors
);
CREATE TABLE IF NOT EXISTS workflows (
    name TEXT PRIMARY KEY,
    definition TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass
class RunRecord:
    id: int
    kind: str
    target_id: str
    name: str
    started_at: str
    duration_s: float
    status: str
    input_count: int
    output_count: int
    output_dir: str
    summary: str
    details: dict[str, Any]


class Database:
    """Thread-safe wrapper (worker threads record runs, the GUI reads them)."""

    def __init__(self, file: Path | str | None = None) -> None:
        self._file = str(file or paths.database_file())
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._file, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(workflows)")}
            if "folder" not in columns:   # databases created before folders existed
                self._conn.execute("ALTER TABLE workflows ADD COLUMN folder TEXT NOT NULL DEFAULT ''")

    def close(self) -> None:
        self._conn.close()

    # -- history ---------------------------------------------------------
    def add_run(
        self,
        *,
        kind: str,
        target_id: str,
        name: str,
        started_at: datetime,
        duration_s: float,
        status: str,
        input_count: int,
        output_count: int,
        output_dir: Path | str,
        summary: str,
        details: dict[str, Any],
    ) -> int:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO runs (kind, target_id, name, started_at, duration_s, status,"
                " input_count, output_count, output_dir, summary, details)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    kind, target_id, name, started_at.isoformat(timespec="seconds"),
                    round(duration_s, 2), status, input_count, output_count, str(output_dir),
                    summary, json.dumps(details, ensure_ascii=False, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def list_runs(self, limit: int = 200) -> list[RunRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunRecord(**{**dict(r), "details": json.loads(r["details"])}) for r in rows]

    def stats(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS runs, COALESCE(SUM(input_count),0) AS files,"
                " COALESCE(SUM(status IN ('success','warning')),0) AS ok FROM runs"
            ).fetchone()
        return {"runs": row["runs"], "files": row["files"], "ok": row["ok"]}

    def target_stats(self) -> dict[str, dict[str, Any]]:
        """Per tool/workflow: number of runs, completed runs and the latest run."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT target_id, COUNT(*) AS runs, SUM(status IN ('success','warning')) AS ok,"
                " MAX(id) AS last_id FROM runs GROUP BY target_id").fetchall()
            result = {}
            for row in rows:
                last = self._conn.execute(
                    "SELECT started_at, summary, status FROM runs WHERE id=?", (row["last_id"],)).fetchone()
                result[row["target_id"]] = {"runs": row["runs"], "ok": row["ok"] or 0, **dict(last)}
        return result

    def clear_runs(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM runs")

    # -- workflows -------------------------------------------------------
    def save_workflow(self, name: str, definition: dict[str, Any], folder: str | None = None) -> None:
        """Save or update a workflow. ``folder=None`` keeps the folder it is already in."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO workflows (name, definition, updated_at, folder) VALUES (?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET definition=excluded.definition,"
                " updated_at=excluded.updated_at"
                + (", folder=excluded.folder" if folder is not None else ""),
                (name, json.dumps(definition, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds"), (folder or "").strip()),
            )

    def workflow_entries(self) -> list[dict[str, Any]]:
        """Saved workflows with their folder and last change."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, folder, definition, updated_at FROM workflows ORDER BY folder, name").fetchall()
        return [{"name": r["name"], "folder": r["folder"], "updated_at": r["updated_at"],
                 "definition": json.loads(r["definition"])} for r in rows]

    def move_workflow(self, name: str, folder: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE workflows SET folder=? WHERE name=?", (folder.strip(), name))

    def rename_folder(self, old: str, new: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE workflows SET folder=? WHERE folder=?", (new.strip(), old))
            self._conn.execute("UPDATE workflows SET folder=? || substr(folder, ?) WHERE folder LIKE ?",
                               (new.strip(), len(old) + 1, old + "/%"))

    def list_workflows(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT name FROM workflows ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def load_workflow(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT definition FROM workflows WHERE name=?", (name,)
            ).fetchone()
        return json.loads(row["definition"]) if row else None

    def delete_workflow(self, name: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM workflows WHERE name=?", (name,))
