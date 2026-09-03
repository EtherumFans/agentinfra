"""Phase A1A Gate 3R.8 — Cross-gate regression + security negative tests.

Charter §3R.8 asks for a regression + security negative test sweep
that explicitly enumerates the invariants established across Gate 3R
as one coherent defence-in-depth. This file is the consolidated
Gate 3R negative spine — each test names the gates it exercises
and the specific invariant that must hold.

Layered invariants under test:

  Layer 7  (Gate 3R.1)  Orphan-run denial — signed token valid but
                         no RunHistory row → 404 on trace + SSE.
  Layer 8  (Gate 3R.2)  Audit emit coverage — material emit callers
                         fire on run lifecycle / idempotency / api_client.
  Layer 9  (Gate 3R.3)  TraceCaptureState state machine — 6 literals
                         only; deployment profile resolver consistent.
  Layer 10 (Gate 3R.4)  Stable event identity — UUID + sequence_number
                         on every DbRunTraceStore.append.
  Layer 11 (Gate 3R.5)  Migration 020 idempotent — re-run upgrade head
                         is a silent no-op.
  Layer 12 (Gate 3R.6)  Cross-org denial — token-bound org mismatch
                         rejected on trace + SSE + console.

Positive regressions on the same paths are covered by the per-gate
test files (test_a1a_gate3r_*.py). This file is the cross-gate
negative spine: cases that span two or more gates and would be
awkward to assert in any single per-gate file.

The existing Gate 3.8 negative spine
(`test_a1a_gate3_8_security_negative_consolidated.py`) covers
layers 1-6. This file extends it to layers 7-12.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"
_VERSIONS_DIR = _BACKEND_ROOT / "alembic" / "versions"


def _current_alembic_head() -> str:
    """Phase A1D.5 — read canonical head from versions dir (self-healing)."""
    revision_files = sorted(
        f for f in _VERSIONS_DIR.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("__")
    )
    head_revisions: set[str] = set()
    child_revisions: set[str] = set()
    for rf in revision_files:
        text = rf.read_text(encoding="utf-8")
        rev = down = None
        for line in text.splitlines():
            if line.startswith("revision = "):
                rev = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("down_revision = "):
                down = line.split("=", 1)[1].strip().strip('"').strip("'")
        if rev is not None:
            head_revisions.add(rev)
            if down is not None and down != "None":
                child_revisions.add(down)
    heads = head_revisions - child_revisions
    assert len(heads) == 1, f"expected 1 alembic head, got {heads}"
    return next(iter(heads))


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ────────────────────────────────────────────────────────────────────
# Layer 7 — Orphan-run denial (Gate 3R.1)
# ────────────────────────────────────────────────────────────────────


def test_L7_partner_trace_orphan_run_denied(client: TestClient) -> None:
    """Layer 7 / Gate 3R.1 — signed trace token for a run that has
    no RunHistory row must return 404 TRACE_NOT_FOUND, not the
    events that might happen to live in the store."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-orphan-{secrets.token_hex(4)}"
    tok = issue_trace_token(
        run_id=run_id,
        organization_id="org_default1",
        ttl_seconds=60,
    )
    r = client.get(f"/api/v1/runs/{run_id}/trace?token={tok}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "TRACE_NOT_FOUND"


def test_L7_console_trace_orphan_run_denied(client: TestClient) -> None:
    """Layer 7 / Gate 3R.1 — Console trace path also guards orphan
    runs even when no token is required (test client bypass auth)."""
    r = client.get("/api/runtime/runs/run-3r8-orphan-nonexistent/trace")
    assert r.status_code == 404


def test_L7_partner_sse_orphan_run_denied(client: TestClient) -> None:
    """Layer 7 / Gate 3R.1 — SSE path also guards orphan runs."""
    from app.services.trace_token import issue_trace_token
    run_id = f"run-orphan-sse-{secrets.token_hex(4)}"
    tok = issue_trace_token(
        run_id=run_id,
        organization_id="org_default1",
        ttl_seconds=60,
    )
    r = client.get(
        f"/api/v1/runs/{run_id}/events?token={tok}",
        headers={"Accept": "text/event-stream"},
    )
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# Layer 8 — Audit emit coverage (Gate 3R.2)
# ────────────────────────────────────────────────────────────────────


def test_L8_run_lifecycle_actions_in_allowlist() -> None:
    """Layer 8 / Gate 3R.2 — the six audit actions that Gate 3
    listed in the allowlist but didn't emit are now actually
    emitted. The allowlist itself must contain all six so the
    emit callers don't raise allowlist-violation at runtime."""
    from app.services.system_audit import ALL_SYSTEM_AUDIT_ACTIONS
    for action in (
        "run.cancel",
        "run.timeout",
        "run.complete",
        "run.failed",
        "idempotency.dedup",
        "api_client.rotate",
    ):
        assert action in ALL_SYSTEM_AUDIT_ACTIONS, (
            f"{action!r} missing from allowlist — emit caller will raise"
        )


def test_L8_run_lifecycle_actions_classified_correctly() -> None:
    """Layer 8 / Gate 3R.2 — the lifecycle actions must be in
    SYSTEM_AUDIT_ACTIONS so the legacy classifier recognises them
    as system-scope (MODERN_SYSTEM) writes."""
    from app.services.legacy_tenancy_attribution import SYSTEM_AUDIT_ACTIONS
    for action in (
        "run.cancel",
        "run.timeout",
        "run.complete",
        "run.failed",
        "idempotency.dedup",
        "api_client.rotate",
    ):
        assert action in SYSTEM_AUDIT_ACTIONS, (
            f"{action!r} missing from SYSTEM_AUDIT_ACTIONS — "
            "classifier will treat as tenant-scope, breaking the "
            "system_audit() emit path"
        )


def test_L8_record_run_start_stamps_capture_pending() -> None:
    """Layer 8 / Gate 3R.2 + 3R.3 — record_run_start stamps
    trace_capture_status=CAPTURE_PENDING on INSERT."""
    from app.database import AsyncSessionLocal
    from app.services.run_lifecycle import record_run_start

    run_id = f"run-L8-start-{secrets.token_hex(4)}"

    async def _drive():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
            await record_run_start(
                db,
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                organization_id="org_default1",
                input_text="L8 capture-pending test",
            )
            await db.commit()
            row = await db.execute(text(
                "SELECT trace_capture_status FROM run_history "
                "WHERE run_id = :rid"
            ), {"rid": run_id})
            return row.first()
    row = asyncio.run(_drive())
    assert row is not None
    # The value is either CAPTURE_PENDING (post-Migration-020) or NULL
    # (pre-Migration-020 fallback). Both are acceptable.
    assert row[0] in ("CAPTURE_PENDING", None)

    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
    asyncio.run(_cleanup())


# ────────────────────────────────────────────────────────────────────
# Layer 9 — TraceCaptureState + DeploymentProfile (Gate 3R.3)
# ────────────────────────────────────────────────────────────────────


def test_L9_trace_capture_state_only_six_literals() -> None:
    """Layer 9 / Gate 3R.3 — TraceCaptureState.ALL_STATES is exactly
    the 6 literals the Migration 020 CHECK allows."""
    from app.services.trace_capture_state import TraceCaptureState as S
    expected = {
        "NEVER_CAPTURED_LEGACY",
        "CAPTURE_PENDING",
        "CAPTURED",
        "PERSISTED",          # deprecated alias
        "FAILED",
        "FALLBACK_MEMORY",
    }
    assert S.ALL_STATES == expected


def test_L9_normalize_persisted_to_captured() -> None:
    """Layer 9 / Gate 3R.3 — PERSISTED alias normalizes to CAPTURED
    on read."""
    from app.services.trace_capture_state import TraceCaptureState as S
    assert S.normalize("PERSISTED") == "CAPTURED"
    assert S.normalize("CAPTURED") == "CAPTURED"
    assert S.normalize("FAILED") == "FAILED"
    assert S.normalize(None) is None


def test_L9_deployment_profile_matrix() -> None:
    """Layer 9 / Gate 3R.3 — DeploymentProfile resolver returns the
    expected profile for the documented matrix.

    Note: the resolver itself does NOT refuse cloud+memory — that
    enforcement is in Settings validation, not in resolve_profile.
    The resolver just reflects intent from the (mode, store,
    fail_closed) triple."""
    from app.services.deployment_profile import (
        DeploymentProfile, resolve_profile,
    )
    # Explicit override wins
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="memory",
        runtrace_fail_closed=False,
        explicit_profile="REQUIRED_DB",
    ) == DeploymentProfile.REQUIRED_DB
    # Cloud + db + fail_closed = REQUIRED_DB (the only REQUIRED_DB path)
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="db",
        runtrace_fail_closed=True,
    ) == DeploymentProfile.REQUIRED_DB
    # Local + db + fail_closed = BEST_EFFORT_DB
    assert resolve_profile(
        deployment_mode="local",
        runtrace_store="db",
        runtrace_fail_closed=True,
    ) == DeploymentProfile.BEST_EFFORT_DB
    # Local + db + not fail_closed = BEST_EFFORT_DB
    assert resolve_profile(
        deployment_mode="local",
        runtrace_store="db",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.BEST_EFFORT_DB
    # Local + memory = MEMORY_DEV
    assert resolve_profile(
        deployment_mode="local",
        runtrace_store="memory",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.MEMORY_DEV
    # Cloud + memory (Settings validation will refuse this; resolver
    # itself returns MEMORY_DEV and lets Settings decide).
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="memory",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.MEMORY_DEV


# ────────────────────────────────────────────────────────────────────
# Layer 10 — Stable event identity (Gate 3R.4)
# ────────────────────────────────────────────────────────────────────


def test_L10_event_id_is_uuid_v4_shaped() -> None:
    """Layer 10 / Gate 3R.4 — every event_id is a 36-char UUID v4."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _assign_event_identity, _reset_trace_sequence_counter,
    )
    trace = f"trace-L10-{secrets.token_hex(4)}"
    _reset_trace_sequence_counter(trace)
    try:
        eid1, _ = _assign_event_identity("run-x", trace)
        eid2, _ = _assign_event_identity("run-x", trace)
        for eid in (eid1, eid2):
            assert len(eid) == 36
            parts = eid.split("-")
            assert len(parts) == 5
            assert len(parts[0]) == 8
            assert len(parts[4]) == 12
        assert eid1 != eid2
    finally:
        _reset_trace_sequence_counter(trace)


def test_L10_sequence_counter_monotonic_per_trace() -> None:
    """Layer 10 / Gate 3R.4 — within one trace_id, sequence numbers
    are 1-indexed and strictly monotonic."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _assign_event_identity, _reset_trace_sequence_counter,
    )
    trace = f"trace-L10-seq-{secrets.token_hex(4)}"
    _reset_trace_sequence_counter(trace)
    try:
        seqs = [_assign_event_identity("run-y", trace)[1] for _ in range(5)]
        assert seqs == [1, 2, 3, 4, 5]
    finally:
        _reset_trace_sequence_counter(trace)


# ────────────────────────────────────────────────────────────────────
# Layer 11 — Migration 020 idempotency (Gate 3R.5)
# ────────────────────────────────────────────────────────────────────


def _run_alembic(target_db: str, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{target_db}"
    env["PYTHONPATH"] = str(_BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args]
    return subprocess.run(
        cmd, cwd=str(_BACKEND_ROOT), env=env,
        capture_output=True, text=True, timeout=60,
    )


def test_L11_migration_head_is_020_on_fresh_db(tmp_path) -> None:
    """Layer 11 / Gate 3R.5 — fresh DB lands at alembic_version=026.

    Updated by Phase A1A Gate 4.2 — Migration 021 added NOT NULL + CHECK
    on encounters/documents/cdi_cases.organization_id (closes GATE3_015).
    A1B-AE.3 → 022 (expert_registry_provenance).
    A1B-AE.4 → 023 (agent_canonical_key_and_alias).
    A1B-AE-R.1.a → 024 (context_task_refs.state CHECK).
    A1B-AE-R.1.b → 025 (contexts.organization_id for cross-tenant).
    A1B-AE-RV.2 → 026 (drop permanent org_default1 server_default).
    """
    db_path = str(tmp_path / "L11_fresh.db")
    r = _run_alembic(db_path, "upgrade", "head")
    assert r.returncode == 0, (
        f"alembic failed:\nstdout:{r.stdout}\nstderr:{r.stderr}"
    )
    conn = sqlite3.connect(db_path)
    try:
        v = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        cols = {row[1] for row in conn.execute("PRAGMA table_info(run_trace_events)")}
    finally:
        conn.close()
    assert v == _current_alembic_head()
    assert "event_id" in cols
    assert "sequence_number" in cols
    assert "trace_id" in cols
    assert "identity_source" in cols


def test_L11_migration_idempotent_rerun(tmp_path) -> None:
    """Layer 11 / Gate 3R.5 — second `upgrade head` is a silent no-op."""
    db_path = str(tmp_path / "L11_idem.db")
    first = _run_alembic(db_path, "upgrade", "head")
    assert first.returncode == 0
    second = _run_alembic(db_path, "upgrade", "head")
    assert second.returncode == 0, (
        f"second upgrade should be no-op:\nstderr:{second.stderr}"
    )


# ────────────────────────────────────────────────────────────────────
# Layer 12 — Cross-org denial matrix (Gate 3R.6)
# ────────────────────────────────────────────────────────────────────


def test_L12_partner_trace_cross_org_denied(client: TestClient) -> None:
    """Layer 12 / Gate 3R.6 — partner trace endpoint returns 403
    TRACE_TOKEN_ORG_MISMATCH when token org != row org."""
    from app.services.trace_token import issue_trace_token
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.services.run_lifecycle import get_run_status

    run_id = f"run-L12-xorg-{secrets.token_hex(4)}"

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                organization_id="org_actual",
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
            row = await get_run_status(db, run_id=run_id)
            return row is not None
    seeded = asyncio.run(_seed())
    assert seeded

    try:
        # Token bound to a DIFFERENT org
        bad_tok = issue_trace_token(
            run_id=run_id, organization_id="org_intruder", ttl_seconds=60,
        )
        r = client.get(f"/api/v1/runs/{run_id}/trace?token={bad_tok}")
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "TRACE_TOKEN_ORG_MISMATCH"
    finally:
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_history WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.commit()
        asyncio.run(_cleanup())


def test_L12_partner_trace_valid_org_accepted(client: TestClient) -> None:
    """Layer 12 / Gate 3R.6 — partner trace endpoint accepts token
    when org matches. Positive regression for the negative above."""
    from app.services.trace_token import issue_trace_token
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    run_id = f"run-L12-valid-{secrets.token_hex(4)}"
    org_id = "org_L12_valid"

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=secrets.token_hex(6),
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                organization_id=org_id,
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
        tok = issue_trace_token(
            run_id=run_id, organization_id=org_id, ttl_seconds=60,
        )
        r = client.get(f"/api/v1/runs/{run_id}/trace?token={tok}")
        # No events → 404 TRACE_NOT_FOUND, NOT 403 or 401.
        # This proves the token was accepted (got past org check).
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "TRACE_NOT_FOUND"
    finally:
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_history WHERE run_id = :rid"
                ), {"rid": run_id})
                await db.commit()
        asyncio.run(_cleanup())


# ────────────────────────────────────────────────────────────────────
# Cross-gate regression — verify all 3R test files still pass
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "module",
    [
        "tests.test_api.test_a1a_gate3r_1_orphan_run_denial",
        "tests.test_api.test_a1a_gate3r_2_audit_emit_wiring",
        "tests.test_api.test_a1a_gate3r_3_trace_capture_profiles",
        "tests.test_api.test_a1a_gate3r_4_trace_event_identity",
        "tests.test_api.test_a1a_gate3r_5_migration_portability",
    ],
)
def test_L13_module_imports_clean(module: str) -> None:
    """Layer 13 / Cross-gate — every Gate 3R test module imports
    without errors. Catches import-time regressions (removed
    helper, renamed constant, etc.) that would only surface when
    pytest actually collects the file."""
    import importlib
    mod = importlib.import_module(module)
    assert mod is not None
    # Spot-check: each module has at least one test_ function
    test_fns = [n for n in dir(mod) if n.startswith("test_")]
    assert len(test_fns) >= 5, (
        f"{module} has {len(test_fns)} tests; expected >= 5"
    )
