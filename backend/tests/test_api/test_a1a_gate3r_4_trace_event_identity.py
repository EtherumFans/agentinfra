"""Phase A1A Gate 3R.4 — Stable trace event identity (Migration 020).

Charter §3R.4: replace the brittle (run_id, step, ts) composite
identity with a canonical event_id UUID + per-trace sequence_number.

Note on test environment: the test DB is built via
``Base.metadata.create_all`` (see conftest.py), NOT via ``alembic
upgrade head``. This means:
  - The new columns DO appear (model definition has them)
  - The CHECK constraint widening does NOT appear (it lives in the
    migration only)
  - The NULL → NEVER_CAPTURED_LEGACY backfill does NOT run

Migration-level artifacts (CHECK widening, backfill, alembic_version
bump) are verified manually via ``alembic upgrade head`` against the
dev DB at ``data/icoder.db`` — see closure report §3.2 for the
post-migration schema dump. The tests here focus on code-level
behavior that the migration enables.

§1 Model definition — new columns on RunTraceEventModel
§2 Migration 020 module — syntactically valid, correct revision chain
§3 _assign_event_identity helper — UUID + sequence_number
§4 DbRunTraceStore.append populates new columns
§5 Sequence counter keys on trace_id (falls back to run_id)
§6 Backwards compat — readers continue to work with NULL event_id
"""
from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, UTC

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ────────────────────────────────────────────────────────────────────
# §1 Model definition — new columns
# ────────────────────────────────────────────────────────────────────


def test_model_has_new_identity_columns() -> None:
    """RunTraceEventModel has the four new columns added by Gate 3R.4."""
    from app.models.run_trace import RunTraceEventModel
    cols = {c.name for c in RunTraceEventModel.__table__.columns}
    assert "event_id" in cols
    assert "sequence_number" in cols
    assert "trace_id" in cols
    assert "identity_source" in cols


def test_model_new_columns_are_nullable() -> None:
    """New columns are nullable so the migration is online (old readers
    don't need to populate them on INSERT)."""
    from app.models.run_trace import RunTraceEventModel
    for col_name in ("event_id", "sequence_number", "trace_id", "identity_source"):
        col = RunTraceEventModel.__table__.columns[col_name]
        assert col.nullable is True, (
            f"{col_name} should be nullable for online migration compat"
        )


# ────────────────────────────────────────────────────────────────────
# §2 Migration 020 module
# ────────────────────────────────────────────────────────────────────


def test_migration_020_imports_cleanly() -> None:
    """Migration 020 module loads without errors and has correct
    revision metadata."""
    import importlib.util
    from pathlib import Path
    migration_path = (
        Path(__file__).parent.parent.parent
        / "alembic" / "versions" / "020_trace_event_identity_and_capture_state.py"
    )
    assert migration_path.exists(), f"migration file missing: {migration_path}"
    spec = importlib.util.spec_from_file_location("migration_020", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "020"
    assert mod.down_revision == "019"


def test_migration_020_has_upgrade_and_downgrade() -> None:
    """Both upgrade() and downgrade() are defined."""
    import importlib.util
    from pathlib import Path
    migration_path = (
        Path(__file__).parent.parent.parent
        / "alembic" / "versions" / "020_trace_event_identity_and_capture_state.py"
    )
    spec = importlib.util.spec_from_file_location("migration_020", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


# ────────────────────────────────────────────────────────────────────
# §3 _assign_event_identity helper
# ────────────────────────────────────────────────────────────────────


def test_assign_identity_returns_uuid_v4_shaped_event_id() -> None:
    """event_id is a 36-char UUID v4 string (8-4-4-4-12 hex groups)."""
    from app.icoder.agent_runtime.orchestrator.run_trace import _assign_event_identity
    eid, seq = _assign_event_identity("run-x", "trace-x")
    assert eid is not None
    assert len(eid) == 36
    parts = eid.split("-")
    assert len(parts) == 5
    assert len(parts[0]) == 8
    assert len(parts[1]) == 4
    assert len(parts[2]) == 4
    assert len(parts[3]) == 4
    assert len(parts[4]) == 12


def test_assign_identity_two_calls_produce_different_uuids() -> None:
    """Each call returns a fresh UUID — no reuse."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _assign_event_identity, _reset_trace_sequence_counter,
    )
    _reset_trace_sequence_counter("trace-y")
    try:
        eid1, _ = _assign_event_identity("run-y", "trace-y")
        eid2, _ = _assign_event_identity("run-y", "trace-y")
        assert eid1 != eid2
    finally:
        _reset_trace_sequence_counter("trace-y")


# ────────────────────────────────────────────────────────────────────
# §4 DbRunTraceStore.append populates new columns
# ────────────────────────────────────────────────────────────────────


def test_db_store_append_populates_identity_columns(client: TestClient) -> None:
    """DbRunTraceStore.append writes event_id, sequence_number, trace_id,
    and identity_source on the new run_trace_events row."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.config import settings
    from app.icoder.agent_runtime.orchestrator import run_trace as rt_mod
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, RunTraceStep, _reset_trace_sequence_counter,
    )

    # Force DB store
    original = settings.RUNTRACE_STORE
    settings.RUNTRACE_STORE = "db"
    rt_mod._DEFAULT_DB_STORE = None

    run_id = f"run-3r4-id-{secrets.token_hex(4)}"
    trace_id = f"trace-3r4-{secrets.token_hex(4)}"
    _reset_trace_sequence_counter(trace_id)

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.execute(text(
                "DELETE FROM run_trace_events WHERE run_id = :rid"
            ), {"rid": run_id})
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                organization_id="org_default1",
                tenancy_classification="MODERN",
                status="COMPLETED",
                latency_ms=0,
                cost_usd=0.0,
                input_text="",
                output_summary="",
                error=False,
                created_at=now,
                updated_at=now,
            ))
            await db.commit()
    asyncio.run(_seed())

    try:
        store = rt_mod.get_default_store()
        store.append(RunTraceEvent(
            run_id=run_id, step=RunTraceStep.USER_MESSAGE_RECEIVED,
            status="ok", ts=1.0,
            safe_metadata={"_trace_id": trace_id},
        ))
        store.append(RunTraceEvent(
            run_id=run_id, step=RunTraceStep.OUTPUT_GENERATED,
            status="ok", ts=2.0,
            safe_metadata={"_trace_id": trace_id},
        ))

        async def _fetch():
            async with AsyncSessionLocal() as db:
                r = await db.execute(text(
                    "SELECT event_id, sequence_number, trace_id, identity_source "
                    "FROM run_trace_events WHERE run_id = :rid "
                    "ORDER BY sequence_number"
                ), {"rid": run_id})
                return [(row[0], row[1], row[2], row[3]) for row in r]
        rows = asyncio.run(_fetch())
        assert len(rows) == 2, f"expected 2 events, got {len(rows)}"

        e1_id, e1_seq, e1_trace, e1_src = rows[0]
        assert e1_id is not None and len(e1_id) == 36
        assert e1_seq == 1
        assert e1_trace == trace_id
        assert e1_src == "uuid_v4"

        e2_id, e2_seq, e2_trace, e2_src = rows[1]
        assert e2_id is not None and len(e2_id) == 36
        assert e2_seq == 2
        assert e2_trace == trace_id
        assert e2_src == "uuid_v4"
        assert e1_id != e2_id
    finally:
        settings.RUNTRACE_STORE = original
        rt_mod._DEFAULT_DB_STORE = None
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_trace_events WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.execute(text(
                    "DELETE FROM run_history WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.commit()
        asyncio.run(_cleanup())
        _reset_trace_sequence_counter(trace_id)


def test_db_store_append_without_trace_id_writes_null_trace() -> None:
    """When safe_metadata doesn't carry _trace_id, the row's trace_id
    column stays NULL but event_id + sequence_number still populate."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.config import settings
    from app.icoder.agent_runtime.orchestrator import run_trace as rt_mod
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, RunTraceStep, _reset_trace_sequence_counter,
    )

    original = settings.RUNTRACE_STORE
    settings.RUNTRACE_STORE = "db"
    rt_mod._DEFAULT_DB_STORE = None

    run_id = f"run-3r4-notrace-{secrets.token_hex(4)}"
    _reset_trace_sequence_counter(run_id)

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.execute(text(
                "DELETE FROM run_trace_events WHERE run_id = :rid"
            ), {"rid": run_id})
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                organization_id="org_default1",
                tenancy_classification="MODERN",
                status="COMPLETED",
                latency_ms=0,
                cost_usd=0.0,
                input_text="",
                output_summary="",
                error=False,
                created_at=now,
                updated_at=now,
            ))
            await db.commit()
    asyncio.run(_seed())

    try:
        store = rt_mod.get_default_store()
        store.append(RunTraceEvent(
            run_id=run_id, step=RunTraceStep.USER_MESSAGE_RECEIVED,
            status="ok", ts=1.0,
            # no _trace_id in safe_metadata
            safe_metadata={"agent_id": "medical-coding-agent"},
        ))

        async def _fetch():
            async with AsyncSessionLocal() as db:
                r = await db.execute(text(
                    "SELECT event_id, sequence_number, trace_id "
                    "FROM run_trace_events WHERE run_id = :rid"
                ), {"rid": run_id})
                return r.first()
        row = asyncio.run(_fetch())
        assert row is not None
        assert row[0] is not None  # event_id populated
        assert row[1] == 1          # sequence_number populated
        assert row[2] is None       # trace_id NULL (no _trace_id in metadata)
    finally:
        settings.RUNTRACE_STORE = original
        rt_mod._DEFAULT_DB_STORE = None
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_trace_events WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.execute(text(
                    "DELETE FROM run_history WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.commit()
        asyncio.run(_cleanup())
        _reset_trace_sequence_counter(run_id)


# ────────────────────────────────────────────────────────────────────
# §5 Sequence counter keys on trace_id (falls back to run_id)
# ────────────────────────────────────────────────────────────────────


def test_sequence_counter_keys_on_trace_id() -> None:
    """Two events with the same run_id but DIFFERENT trace_id get
    sequence numbers from independent counters."""
    from app.icoder.agent_runtime.orchestrator import run_trace as rt

    run_id = "run-3r4-tracekey"
    trace_a = "trace-A"
    trace_b = "trace-B"
    rt._reset_trace_sequence_counter(trace_a)
    rt._reset_trace_sequence_counter(trace_b)
    rt._reset_trace_sequence_counter(run_id)

    try:
        _, seq1 = rt._assign_event_identity(run_id, trace_a)
        _, seq2 = rt._assign_event_identity(run_id, trace_b)
        _, seq3 = rt._assign_event_identity(run_id, trace_a)

        assert seq1 == 1
        assert seq2 == 1
        assert seq3 == 2
    finally:
        rt._reset_trace_sequence_counter(trace_a)
        rt._reset_trace_sequence_counter(trace_b)
        rt._reset_trace_sequence_counter(run_id)


def test_sequence_counter_falls_back_to_run_id_when_no_trace() -> None:
    """When trace_id is None, the counter keys on run_id alone."""
    from app.icoder.agent_runtime.orchestrator import run_trace as rt

    run_id = "run-3r4-notrace"
    rt._reset_trace_sequence_counter(run_id)

    try:
        _, seq1 = rt._assign_event_identity(run_id, None)
        _, seq2 = rt._assign_event_identity(run_id, None)
        assert seq1 == 1
        assert seq2 == 2
    finally:
        rt._reset_trace_sequence_counter(run_id)


# ────────────────────────────────────────────────────────────────────
# §6 Backwards compat — readers continue to work with NULL event_id
# ────────────────────────────────────────────────────────────────────


def test_legacy_read_path_still_works_with_null_event_id() -> None:
    """Pre-3R.4 rows (NULL event_id) are still readable via the
    existing get_run() / get_run_scoped() methods — they don't
    require event_id to be populated."""
    from app.database import AsyncSessionLocal
    from app.models.run_trace import RunTraceEventModel
    from app.config import settings
    from app.icoder.agent_runtime.orchestrator import run_trace as rt_mod

    original = settings.RUNTRACE_STORE
    settings.RUNTRACE_STORE = "db"
    rt_mod._DEFAULT_DB_STORE = None

    run_id = f"run-3r4-legacy-{secrets.token_hex(4)}"

    async def _seed_legacy_row():
        """Insert a row directly via ORM with NULL event_id (simulates
        a pre-Migration-020 row)."""
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_trace_events WHERE run_id = :rid"
            ), {"rid": run_id})
            db.add(RunTraceEventModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                step="ingest",
                status="ok",
                ts=1.0,
                duration_ms=10.0,
                # event_id, sequence_number, trace_id, identity_source
                # all left NULL — simulates pre-3R.4 row
            ))
            await db.commit()
    asyncio.run(_seed_legacy_row())

    try:
        store = rt_mod.get_default_store()
        events = store.get_run(run_id)
        assert len(events) == 1
        assert events[0].step == "ingest"
        assert events[0].status == "ok"
    finally:
        settings.RUNTRACE_STORE = original
        rt_mod._DEFAULT_DB_STORE = None
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_trace_events WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.commit()
        asyncio.run(_cleanup())


# ────────────────────────────────────────────────────────────────────
# §7 Regression — TraceCaptureState still recognizes all 6 literals
# ────────────────────────────────────────────────────────────────────


def test_trace_capture_state_allowlist_unchased_post_migration() -> None:
    """Migration 020 widens the CHECK to include all 6 literals.
    TraceCaptureState.ALL_STATES is the source of truth — verify
    it matches the widened CHECK exactly."""
    from app.services.trace_capture_state import TraceCaptureState as S
    expected = {
        "NEVER_CAPTURED_LEGACY",
        "CAPTURE_PENDING",
        "CAPTURED",
        "PERSISTED",
        "FAILED",
        "FALLBACK_MEMORY",
    }
    assert S.ALL_STATES == expected, (
        f"ALL_STATES drifted from migration CHECK: {S.ALL_STATES}"
    )
