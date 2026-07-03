"""RunStore — persistence + audit for coding-review runs (Runtime-Core observability).

Zero-dep: stdlib ``sqlite3`` only. The full RunResult is serialized to a JSON ``blob``
column (pydantic v2 round-trip); a few columns are denormalized out for the history list.
An append-only ``audit_log`` records who ran / viewed / reviewed what.

Thread-safe: FastAPI runs the sync endpoints in a threadpool, so the single connection is
opened ``check_same_thread=False`` and every method serializes on a ``threading.Lock``.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from .types import RunResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id                TEXT PRIMARY KEY,
    agent_id              TEXT,
    agent_version         TEXT,
    created_at            REAL,
    passed                INTEGER,
    human_review_required INTEGER,
    primary_code          TEXT,
    drg                   TEXT,
    dip_code              TEXT,
    reviewed              INTEGER DEFAULT 0,
    blob                  TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    ts          REAL,
    actor_role  TEXT,
    actor_token TEXT,
    action      TEXT,
    detail      TEXT
);
"""

_SUMMARY_COLS = (
    "run_id", "agent_id", "agent_version", "created_at",
    "passed", "human_review_required",
    "primary_code", "drg", "dip_code", "reviewed",
)


class RunStore:
    """Persists RunResults and an append-only audit trail in one sqlite file."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- runs ---
    def save_run(self, run: RunResult) -> None:
        primary_code = next((c.code for c in run.codes if c.is_primary), None)
        if primary_code is None and run.codes:
            primary_code = run.codes[0].code
        drg = run.drg_route.drg if run.drg_route else None
        dip_code = run.drg_route.dip_code if run.drg_route else None
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO runs
                   (run_id, agent_id, agent_version, created_at,
                    passed, human_review_required,
                    primary_code, drg, dip_code, reviewed, blob)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.run_id, run.agent_id, run.agent_version, run.created_at,
                    int(run.compliance.passed), int(run.compliance.human_review_required),
                    primary_code, drg, dip_code,
                    int(run.human_review is not None),
                    run.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> RunResult | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT blob FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return RunResult.model_validate_json(row["blob"])

    def list_runs(self, limit: int = 50, offset: int = 0,
                  agent_id: str | None = None) -> list[dict]:
        cols = ", ".join(_SUMMARY_COLS)
        where = "WHERE agent_id = ? " if agent_id else ""
        params: tuple = (agent_id, limit, offset) if agent_id else (limit, offset)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {cols} FROM runs {where}"
                "ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    # --- audit ---
    def append_audit(self, run_id: str, actor: dict, action: str, detail: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO audit_log
                   (run_id, ts, actor_role, actor_token, action, detail)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, time.time(), actor.get("role"), actor.get("token"),
                 action, json.dumps(detail, ensure_ascii=False)),
            )
            self._conn.commit()

    def get_audit(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, run_id, ts, actor_role, actor_token, action, detail
                   FROM audit_log WHERE run_id = ? ORDER BY id ASC""",
                (run_id,),
            ).fetchall()
        events = []
        for r in rows:
            ev = dict(r)
            ev["detail"] = json.loads(ev["detail"]) if ev["detail"] else {}
            events.append(ev)
        return events
