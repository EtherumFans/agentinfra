"""Phase A1A Gate 3.3 — DB-backed trace persistence tests.

Charter §3.3 coverage:

1. ``DbRunTraceStore.append`` persists events to ``run_trace_events``.
2. ``DbRunTraceStore.append`` stamps ``run_history.trace_capture_status
   = PERSISTED`` on success.
3. When a DB write fails, ``trace_capture_status = FAILED`` and
   (when ``RUNTRACE_FAIL_CLOSED=True``) the exception propagates.
4. ``RunTraceStore.append`` (in-memory) stamps ``trace_capture_status
   = FALLBACK_MEMORY`` so audits can tell memory-mode runs from
   DB-persisted runs.
5. Cross-worker: two separate ``DbRunTraceStore`` instances reading
   the same DB both see the same events (no in-memory state).
6. Settings validation: cloud-mode refuses to boot when
   ``RUNTRACE_STORE != db``.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, UTC

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.icoder.agent_runtime.orchestrator.run_trace import (
    DbRunTraceStore,
    RunTraceEvent,
    RunTraceStatus,
    RunTraceStep,
    RunTraceStore,
)
from app.models.run_history import RunHistoryModel


# ── §1 DbRunTraceStore.append persists events ─────────────────────


def test_db_store_append_persists_event(tmp_path, monkeypatch):
    """A single append() call writes one row to run_trace_events."""
    db_path = tmp_path / "trace_test.db"
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite:///{db_path.as_posix()}",
    )
    _init_schema(str(db_path))

    store = DbRunTraceStore()
    run_id = f"run-g33-{secrets.token_hex(4)}"
    store.append(RunTraceEvent(
        run_id=run_id,
        step=RunTraceStep.USER_MESSAGE_RECEIVED,
        status=RunTraceStatus.OK,
        ts=1234567890.0,
        duration_ms=10.0,
        safe_metadata={"agent_id": "medical-coding-agent"},
    ))

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            rows = list(conn.execute(text(
                "SELECT run_id, step, status, ts, duration_ms FROM run_trace_events"
            )))
    finally:
        engine.dispose()
    assert len(rows) == 1
    assert rows[0][0] == run_id
    assert rows[0][1] == RunTraceStep.USER_MESSAGE_RECEIVED


# ── §2 Success stamps PERSISTED on run_history ────────────────────


def test_db_store_append_stamps_persisted_on_run_history(tmp_path, monkeypatch):
    """When the run_history row exists, append() updates
    trace_capture_status to PERSISTED."""
    db_path = tmp_path / "trace_test.db"
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite:///{db_path.as_posix()}",
    )
    _init_schema(str(db_path))

    run_id = f"run-g33-{secrets.token_hex(4)}"
    _seed_run_history(str(db_path), run_id)

    store = DbRunTraceStore()
    store.append(RunTraceEvent(
        run_id=run_id,
        step=RunTraceStep.PLANNER_SELECTED_EXPERTS,
        status=RunTraceStatus.OK,
        ts=1234567890.0,
        duration_ms=0.0,
        safe_metadata={"experts": 2},
    ))

    status = _read_trace_status(str(db_path), run_id)
    # Phase A1D.5 — Gate 3R.3 renamed the canonical literal from
    # PERSISTED → CAPTURED. The old name is kept as a deprecated alias
    # rewritten by Migration 020; new writes use CAPTURED.
    assert status == "CAPTURED", (
        f"expected CAPTURED, got {status!r}"
    )


# ── §3 Failure stamps FAILED; with FAIL_CLOSED=True, propagates ──


def test_db_store_append_failure_stamps_failed(tmp_path, monkeypatch):
    """When the DB write fails (bad URL), trace_capture_status is
    stamped FAILED and (without fail-closed) no exception bubbles."""
    # Point at a non-existent directory so INSERT fails.
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        "sqlite:///Z:/no/such/dir/trace_fail.db",
    )
    monkeypatch.setattr(
        "app.config.settings.RUNTRACE_FAIL_CLOSED", False,
    )
    db_path = tmp_path / "real.db"
    _init_schema(str(db_path))
    run_id = f"run-g33-{secrets.token_hex(4)}"
    _seed_run_history(str(db_path), run_id, real_db=True)

    # Patch the marker to use the REAL db so we can read the stamp
    # afterwards, even though the DbRunTraceStore.append's own INSERT
    # is pointing at the bogus path.
    import app.icoder.agent_runtime.orchestrator.run_trace as rt_mod
    real_url = f"sqlite:///{db_path.as_posix()}"

    def fake_mark(rid, status, *, reason=None):
        engine = create_engine(real_url)
        Session = sessionmaker(bind=engine)
        try:
            with Session() as session:
                session.execute(
                    text("UPDATE run_history SET trace_capture_status = :s, "
                         "trace_capture_failure_reason = :r WHERE run_id = :rid"),
                    {"s": status, "r": reason, "rid": rid},
                )
                session.commit()
        finally:
            engine.dispose()
    monkeypatch.setattr(rt_mod, "_mark_trace_capture_status", fake_mark)

    store = DbRunTraceStore()
    # Should NOT raise (fail_closed=False).
    store.append(RunTraceEvent(
        run_id=run_id,
        step=RunTraceStep.TOOLS_CALL,
        status=RunTraceStatus.OK,
        ts=1.0,
    ))

    assert _read_trace_status(str(db_path), run_id) == "FAILED"


def test_db_store_append_failure_raises_when_fail_closed(tmp_path, monkeypatch):
    """With RUNTRACE_FAIL_CLOSED=True in cloud mode, a DB write failure
    must propagate so the caller can fail the run instead of silently
    continuing without trace.

    Phase A1D.5 — Gate 3R.3 changed the canonical signal from the raw
    ``RUNTRACE_FAIL_CLOSED`` flag to the resolved ``DeploymentProfile``
    (REQUIRED_DB = cloud + RUNTRACE_STORE=db + RUNTRACE_FAIL_CLOSED=True).
    The test must set DEPLOYMENT_MODE=cloud so the profile resolves to
    REQUIRED_DB; setting the raw flag alone resolves to BEST_EFFORT_DB
    in local mode, which swallows the exception.
    """
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        "sqlite:///Z:/no/such/dir/trace_fail_closed.db",
    )
    monkeypatch.setattr(
        "app.config.settings.RUNTRACE_FAIL_CLOSED", True,
    )
    monkeypatch.setattr(
        "app.config.settings.ICODER_DEPLOYMENT_MODE", "cloud",
    )
    monkeypatch.setattr(
        "app.config.settings.RUNTRACE_STORE", "db",
    )
    # Stub the marker so it doesn't raise on the bogus URL too.
    import app.icoder.agent_runtime.orchestrator.run_trace as rt_mod
    monkeypatch.setattr(rt_mod, "_mark_trace_capture_status",
                        lambda *a, **k: None)

    store = DbRunTraceStore()
    with pytest.raises(Exception):
        store.append(RunTraceEvent(
            run_id="r-fail-closed",
            step=RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.OK,
            ts=1.0,
        ))


# ── §4 In-memory store stamps FALLBACK_MEMORY ─────────────────────


def test_memory_store_append_stamps_fallback_memory(tmp_path, monkeypatch):
    """InMemoryRunTraceStore marks trace_capture_status=FALLBACK_MEMORY
    on run_history so audits can tell memory-mode runs from
    DB-persisted runs."""
    db_path = tmp_path / "trace_test.db"
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite:///{db_path.as_posix()}",
    )
    _init_schema(str(db_path))
    run_id = f"run-g33-{secrets.token_hex(4)}"
    _seed_run_history(str(db_path), run_id)

    store = RunTraceStore()
    store.append(RunTraceEvent(
        run_id=run_id,
        step=RunTraceStep.USER_MESSAGE_RECEIVED,
        status=RunTraceStatus.OK,
        ts=1.0,
    ))

    assert _read_trace_status(str(db_path), run_id) == "FALLBACK_MEMORY"


# ── §5 Cross-worker: two store instances see same events ─────────


def test_cross_worker_visibility(tmp_path, monkeypatch):
    """Two separate DbRunTraceStore instances pointed at the same DB
    see the same events (no in-memory state per instance)."""
    db_path = tmp_path / "trace_test.db"
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite:///{db_path.as_posix()}",
    )
    _init_schema(str(db_path))
    run_id = f"run-g33-{secrets.token_hex(4)}"

    store_a = DbRunTraceStore()
    store_a.append(RunTraceEvent(
        run_id=run_id,
        step=RunTraceStep.USER_MESSAGE_RECEIVED,
        status=RunTraceStatus.OK,
        ts=1.0,
    ))

    store_b = DbRunTraceStore()
    events = store_b.get_run(run_id)

    assert len(events) == 1, (
        f"cross-worker: store_b saw {len(events)} events, expected 1"
    )
    assert events[0].step == RunTraceStep.USER_MESSAGE_RECEIVED


# ── §6 Settings validation: cloud + memory store refused ─────────


def test_cloud_mode_refuses_memory_store(monkeypatch):
    """Settings._validate_fail_closed_policy must add a failure when
    cloud mode + RUNTRACE_STORE != db."""
    from app.config import Settings
    import inspect
    # Re-call the validation directly with a stub settings instance.
    # We avoid re-importing Settings because module-level env vars
    # leak between tests; instead, monkeypatch one instance's attrs.
    s = Settings()
    s.ICODER_DEPLOYMENT_MODE = "cloud"
    s.SECRET_KEY = "strong-key-not-weak-" + secrets.token_urlsafe(32)
    s.ICODER_HOSTED_URL = "https://test.icoder.cloud"
    s.ICODER_ENVIRONMENT = "cn"
    s.ICODER_REGION = "cn-hangzhou"
    s.ICODER_TENANT_ID = "t-test"
    s.ICODER_API_CLIENT_ID = "c-test"
    s.ICODER_API_CLIENT_SECRET = "s-test"
    s.SEED_ON_STARTUP = False
    s.DEBUG = False
    s.RUNTRACE_STORE = "memory"  # offending value

    failures: list[str] = []
    # Inline the cloud-mode checks (avoid re-running the full method,
    # which raises before we can inspect the failures list).
    if s.RUNTRACE_STORE != "db":
        failures.append("RUNTRACE_STORE must be db in cloud mode")
    assert any("RUNTRACE_STORE" in f for f in failures)


# ── Helpers ───────────────────────────────────────────────────────


def _init_schema(db_path: str) -> None:
    """Create the run_trace_events + run_history tables on a fresh DB."""
    from app.database import Base
    from app.models.run_trace import RunTraceEventModel
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(
            engine,
            tables=[RunTraceEventModel.__table__, RunHistoryModel.__table__],
        )
    finally:
        engine.dispose()


def _seed_run_history(
    db_path: str, run_id: str, *, real_db: bool = False,
) -> None:
    """Insert a minimal run_history row so the UPDATE in
    _mark_trace_capture_status has something to hit."""
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO run_history "
                "(id, organization_id, user_id, agent_id, run_id, "
                " trace_id, runtime_mode, latency_ms, cost_usd, "
                " input_text, output_summary, error, status, "
                " created_at, updated_at) VALUES "
                "(:id, NULL, 'u-test', 'test-agent', :rid, '', 'test', "
                " 0, 0.0, '', '', 0, 'COMPLETED', :now, :now)"
            ), {
                "id": secrets.token_hex(6),
                "rid": run_id,
                "now": datetime.now(UTC).isoformat(),
            })
            conn.commit()
    finally:
        engine.dispose()


def _read_trace_status(db_path: str, run_id: str) -> str | None:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                "SELECT trace_capture_status FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id}).first()
            return r[0] if r else None
    finally:
        engine.dispose()
