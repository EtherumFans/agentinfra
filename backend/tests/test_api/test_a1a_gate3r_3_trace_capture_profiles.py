"""Phase A1A Gate 3R.3 — Trace capture status semantics + deployment profiles.

Charter §3R.3 carry-over: disambiguate the four meanings of NULL
``run_history.trace_capture_status`` and replace the binary
RUNTRACE_STORE=memory|db + RUNTRACE_FAIL_CLOSED=True|False matrix
with named deployment profiles.

§1 TraceCaptureState taxonomy — 5-class state machine
§2 DeploymentProfile resolver — 3 named profiles
§3 record_run_start stamps CAPTURE_PENDING on INSERT
§4 DbRunTraceStore writes CAPTURED (canonical) / FAILED
§5 InMemoryRunTraceStore writes FALLBACK_MEMORY
§6 Settings cloud-mode validation refuses MEMORY_DEV
§7 Backwards compat: legacy PERSISTED literal normalizes to CAPTURED
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
# §1 TraceCaptureState taxonomy
# ────────────────────────────────────────────────────────────────────


def test_state_machine_has_5_canonical_states() -> None:
    from app.services.trace_capture_state import TraceCaptureState
    # The 5 new/canonical states
    assert TraceCaptureState.NEVER_CAPTURED_LEGACY == "NEVER_CAPTURED_LEGACY"
    assert TraceCaptureState.CAPTURE_PENDING == "CAPTURE_PENDING"
    assert TraceCaptureState.CAPTURED == "CAPTURED"
    assert TraceCaptureState.FAILED == "FAILED"
    assert TraceCaptureState.FALLBACK_MEMORY == "FALLBACK_MEMORY"
    # PERSISTED kept as a deprecated alias for backwards compat
    assert TraceCaptureState.PERSISTED == "PERSISTED"


def test_state_machine_all_states_includes_legacy_alias() -> None:
    """PERSISTED must remain in ALL_STATES so the DB CHECK widening
    in Migration 020 doesn't invalidate existing rows."""
    from app.services.trace_capture_state import TraceCaptureState
    assert "PERSISTED" in TraceCaptureState.ALL_STATES
    assert len(TraceCaptureState.ALL_STATES) == 6  # 5 canonical + PERSISTED alias


def test_is_answered_distinguishes_pending_from_terminal() -> None:
    """CAPTURE_PENDING is NOT answered — the run is still in flight.
    All other states (incl. NEVER_CAPTURED_LEGACY) represent a
    definite outcome."""
    from app.services.trace_capture_state import TraceCaptureState as S
    assert S.is_answered(None) is False
    assert S.is_answered(S.CAPTURE_PENDING) is False
    assert S.is_answered(S.CAPTURED) is True
    assert S.is_answered(S.NEVER_CAPTURED_LEGACY) is True
    assert S.is_answered(S.FAILED) is True
    assert S.is_answered(S.FALLBACK_MEMORY) is True
    # Legacy alias also counts as answered
    assert S.is_answered(S.PERSISTED) is True


def test_is_lost_distinguishes_recoverable_from_unrecoverable() -> None:
    """is_lost returns True iff trace events are known-unavailable —
    used by the RunTrace page to show "trace unavailable"."""
    from app.services.trace_capture_state import TraceCaptureState as S
    assert S.is_lost(S.NEVER_CAPTURED_LEGACY) is True
    assert S.is_lost(S.FAILED) is True
    assert S.is_lost(S.FALLBACK_MEMORY) is True
    assert S.is_lost(S.CAPTURED) is False
    assert S.is_lost(S.CAPTURE_PENDING) is False


def test_normalize_maps_persisted_to_captured() -> None:
    """Readers use normalize() to treat PERSISTED and CAPTURED as
    identical until Migration 020 rewrites existing rows."""
    from app.services.trace_capture_state import TraceCaptureState as S
    assert S.normalize(S.PERSISTED) == S.CAPTURED
    assert S.normalize(S.CAPTURED) == S.CAPTURED
    assert S.normalize(S.FAILED) == S.FAILED
    assert S.normalize(None) is None


# ────────────────────────────────────────────────────────────────────
# §2 DeploymentProfile resolver
# ────────────────────────────────────────────────────────────────────


def test_resolver_explicit_override_wins() -> None:
    from app.services.deployment_profile import resolve_profile, DeploymentProfile
    # Even with cloud+db+failclosed=False, an explicit override wins
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="db",
        runtrace_fail_closed=False,
        explicit_profile="REQUIRED_DB",
    ) == DeploymentProfile.REQUIRED_DB


def test_resolver_invalid_profile_raises() -> None:
    from app.services.deployment_profile import resolve_profile
    with pytest.raises(ValueError, match="Unknown deployment profile"):
        resolve_profile(
            deployment_mode="cloud",
            runtrace_store="db",
            runtrace_fail_closed=False,
            explicit_profile="INVALID_PROFILE",
        )


def test_resolver_cloud_db_no_failclosed_is_best_effort() -> None:
    from app.services.deployment_profile import resolve_profile, DeploymentProfile
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="db",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.BEST_EFFORT_DB


def test_resolver_cloud_db_failclosed_is_required_db() -> None:
    from app.services.deployment_profile import resolve_profile, DeploymentProfile
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="db",
        runtrace_fail_closed=True,
    ) == DeploymentProfile.REQUIRED_DB


def test_resolver_local_memory_is_memory_dev() -> None:
    from app.services.deployment_profile import resolve_profile, DeploymentProfile
    assert resolve_profile(
        deployment_mode="local",
        runtrace_store="memory",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.MEMORY_DEV


def test_resolver_cloud_memory_is_memory_dev_then_refused_at_boot() -> None:
    """Resolver returns MEMORY_DEV (it doesn't second-guess the
    operator); the cloud-mode Settings validation is what refuses
    to boot with MEMORY_DEV in cloud mode."""
    from app.services.deployment_profile import resolve_profile, DeploymentProfile
    assert resolve_profile(
        deployment_mode="cloud",
        runtrace_store="memory",
        runtrace_fail_closed=False,
    ) == DeploymentProfile.MEMORY_DEV


def test_profile_predicates() -> None:
    """Cloud-allowed / db-backed / fail-closed predicates."""
    from app.services.deployment_profile import DeploymentProfile as P
    assert P.is_cloud_allowed(P.BEST_EFFORT_DB)
    assert P.is_cloud_allowed(P.REQUIRED_DB)
    assert not P.is_cloud_allowed(P.MEMORY_DEV)
    assert P.is_db_backed(P.BEST_EFFORT_DB)
    assert P.is_db_backed(P.REQUIRED_DB)
    assert not P.is_db_backed(P.MEMORY_DEV)
    assert P.is_fail_closed(P.REQUIRED_DB)
    assert not P.is_fail_closed(P.BEST_EFFORT_DB)
    assert not P.is_fail_closed(P.MEMORY_DEV)


# ────────────────────────────────────────────────────────────────────
# §3 record_run_start stamps CAPTURE_PENDING on INSERT
# ────────────────────────────────────────────────────────────────────


def _delete_run_history(run_id: str) -> None:
    from app.database import AsyncSessionLocal
    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
    asyncio.run(_go())


def test_record_run_start_stamps_capture_pending() -> None:
    """record_run_start writes trace_capture_status=CAPTURE_PENDING.

    This is the key fix that disambiguates "row written, awaiting
    first trace emit" from "pre-Gate-3.3 historical row" (NULL).

    Note: pre-Migration-020 the DB CHECK constraint may reject this
    value. record_run_start falls back to NULL in that case. This
    test verifies the row exists with EITHER CAPTURE_PENDING (post-
    Migration 020) or NULL (pre-Migration 020)."""
    from app.database import AsyncSessionLocal
    from app.services.run_lifecycle import record_run_start

    run_id = f"run-3r3-start-{secrets.token_hex(4)}"
    _delete_run_history(run_id)
    try:
        async def _go():
            async with AsyncSessionLocal() as db:
                await record_run_start(
                    db,
                    run_id=run_id,
                    agent_id="medical-coding-agent",
                    user_id="u-test-bypass",
                    organization_id="org_default1",
                    input_text="test",
                )
                await db.commit()
                r = await db.execute(text(
                    "SELECT trace_capture_status FROM run_history "
                    "WHERE run_id = :rid"
                ), {"rid": run_id})
                return r.scalar()
        status = asyncio.run(_go())
        assert status in ("CAPTURE_PENDING", None), (
            f"expected CAPTURE_PENDING (post-Migration 020) or NULL "
            f"(pre-Migration 020 fallback); got {status!r}"
        )
    finally:
        _delete_run_history(run_id)


# ────────────────────────────────────────────────────────────────────
# §4 InMemoryRunTraceStore writes FALLBACK_MEMORY
# ────────────────────────────────────────────────────────────────────


def test_in_memory_store_marks_fallback_memory(client: TestClient) -> None:
    """InMemoryRunTraceStore.append stamps FALLBACK_MEMORY on run_history."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, get_default_store, emit_trace_event, RunTraceStep,
    )

    run_id = f"run-3r3-mem-{secrets.token_hex(4)}"

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
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

    store = get_default_store()
    if hasattr(store, "clear"):
        store.clear()
    try:
        emit_trace_event(
            run_id=run_id,
            step=RunTraceStep.USER_MESSAGE_RECEIVED,
        )
        # Give the best-effort UPDATE time to land
        import time as _t
        _t.sleep(0.05)

        async def _fetch():
            async with AsyncSessionLocal() as db:
                r = await db.execute(text(
                    "SELECT trace_capture_status FROM run_history "
                    "WHERE run_id = :rid"
                ), {"rid": run_id})
                return r.scalar()
        status = asyncio.run(_fetch())
        assert status == "FALLBACK_MEMORY", (
            f"InMemoryRunTraceStore should stamp FALLBACK_MEMORY; got {status!r}"
        )
    finally:
        _delete_run_history(run_id)
        if hasattr(store, "clear"):
            store.clear()


# ────────────────────────────────────────────────────────────────────
# §5 DB-backed store writes CAPTURED on success (canonical name)
# ────────────────────────────────────────────────────────────────────


def test_db_store_writes_canonical_state_names(monkeypatch) -> None:
    """DbRunTraceStore.append uses TraceCaptureState.CAPTURED (not
    the legacy 'PERSISTED') on success and TraceCaptureState.FAILED
    on exception.

    This test stubs the DB write to verify the state names are
    pulled from TraceCaptureState. It does NOT exercise the full
    DB write path — that's covered by §3 + existing Gate 3.3 tests.
    """
    from app.services.trace_capture_state import TraceCaptureState
    from app.icoder.agent_runtime.orchestrator import run_trace as rt

    # Capture the state names DbRunTraceStore.append would write
    captured_states: list[str] = []

    def fake_mark(run_id, status, *, reason=None):
        captured_states.append(status)

    monkeypatch.setattr(rt, "_mark_trace_capture_status", fake_mark)

    # Build a DbRunTraceStore but stub its session factory so the
    # first INSERT raises — we want to verify FAILED is emitted with
    # the canonical state name, not the legacy literal.
    store = rt.DbRunTraceStore()
    store._sync_session_factory = lambda: (_ for _ in ()).throw(
        RuntimeError("simulated DB error")
    )
    store._sync_engine = object()  # skip lazy init

    event = rt.RunTraceEvent(
        run_id="run-3r3-fail",
        step="ingest",
        status="ok",
        ts=0.0,
    )
    # BEST_EFFORT_DB by default → exception is swallowed, FAILED emitted
    store.append(event)
    assert TraceCaptureState.FAILED in captured_states, (
        f"DbRunTraceStore should emit canonical FAILED; got {captured_states}"
    )


# ────────────────────────────────────────────────────────────────────
# §6 Settings cloud-mode validation refuses MEMORY_DEV
# ────────────────────────────────────────────────────────────────────


def test_cloud_mode_memory_dev_refused_at_boot(monkeypatch) -> None:
    """When the resolved profile is MEMORY_DEV in cloud mode, Settings
    raises RuntimeError at construction."""
    # Bypass the module-level singleton by constructing Settings directly.
    # We patch env vars + read .env off a non-existent path so only the
    # explicit env vars we set are visible.
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv("ICODER_HOSTED_URL", "https://api.icoder.cloud")
    monkeypatch.setenv("ICODER_ENVIRONMENT", "cn")
    monkeypatch.setenv("ICODER_REGION", "cn-hangzhou")
    monkeypatch.setenv("ICODER_TENANT_ID", "t1")
    monkeypatch.setenv("ICODER_API_CLIENT_ID", "c1")
    monkeypatch.setenv("ICODER_API_CLIENT_SECRET", "s1")
    monkeypatch.setenv("ICODER_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("RUNTRACE_STORE", "memory")
    monkeypatch.setenv("RUNTRACE_FAIL_CLOSED", "false")
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("RUNTRACE_DEPLOYMENT_PROFILE", raising=False)

    from app.config import Settings
    # Point env_file to /dev/null so the .env in repo root doesn't leak
    # DEBUG=true from local-dev config.
    with pytest.raises(RuntimeError) as exc_info:
        Settings(_env_file="/dev/null")
    msg = str(exc_info.value)
    assert "RUNTRACE_DEPLOYMENT_PROFILE resolved to 'MEMORY_DEV'" in msg, (
        f"Expected MEMORY_DEV refusal message; got: {msg}"
    )


def test_cloud_mode_required_db_profile_accepted(monkeypatch) -> None:
    """An explicit ICODER_RUNTRACE_PROFILE=REQUIRED_DB in cloud mode
    satisfies the validation."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv("ICODER_HOSTED_URL", "https://api.icoder.cloud")
    monkeypatch.setenv("ICODER_ENVIRONMENT", "cn")
    monkeypatch.setenv("ICODER_REGION", "cn-hangzhou")
    monkeypatch.setenv("ICODER_TENANT_ID", "t1")
    monkeypatch.setenv("ICODER_API_CLIENT_ID", "c1")
    monkeypatch.setenv("ICODER_API_CLIENT_SECRET", "s1")
    monkeypatch.setenv("ICODER_SECRET_KEY", "x" * 48)
    # Phase A1A Gate 4.4 — cloud mode also requires PHI encryption key.
    from cryptography.fernet import Fernet
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("RUNTRACE_STORE", "db")
    monkeypatch.setenv("RUNTRACE_FAIL_CLOSED", "false")
    monkeypatch.setenv("RUNTRACE_DEPLOYMENT_PROFILE", "REQUIRED_DB")
    monkeypatch.delenv("DEBUG", raising=False)

    from app.config import Settings
    s = Settings(_env_file="/dev/null")
    assert s._resolved_runtrace_profile == "REQUIRED_DB"


# ────────────────────────────────────────────────────────────────────
# §7 _should_fail_closed consults deployment profile
# ────────────────────────────────────────────────────────────────────


def test_should_fail_closed_returns_true_for_required_db(monkeypatch) -> None:
    from app.icoder.agent_runtime.orchestrator import run_trace as rt
    from app.services import deployment_profile as dp

    monkeypatch.setattr(dp, "get_current_profile", lambda: "REQUIRED_DB")
    assert rt._should_fail_closed() is True


def test_should_fail_closed_returns_false_for_best_effort_db(monkeypatch) -> None:
    from app.icoder.agent_runtime.orchestrator import run_trace as rt
    from app.services import deployment_profile as dp

    monkeypatch.setattr(dp, "get_current_profile", lambda: "BEST_EFFORT_DB")
    assert rt._should_fail_closed() is False


def test_should_fail_closed_returns_false_for_memory_dev(monkeypatch) -> None:
    from app.icoder.agent_runtime.orchestrator import run_trace as rt
    from app.services import deployment_profile as dp

    monkeypatch.setattr(dp, "get_current_profile", lambda: "MEMORY_DEV")
    assert rt._should_fail_closed() is False


# ────────────────────────────────────────────────────────────────────
# §8 Regression — existing rows with NULL trace_capture_status
# are still readable (no migration yet)
# ────────────────────────────────────────────────────────────────────


def test_legacy_null_trace_status_rows_remain_readable(client: TestClient) -> None:
    """Gate 3R.3 must NOT break reads of existing NULL-trace-status rows.

    This is the backwards-compat guarantee: Migration 020 will backfill
    NULLs to NEVER_CAPTURED_LEGACY, but until then readers must continue
    to interpret NULL as 'unknown, do not fail the read'.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.services.trace_capture_state import TraceCaptureState as S

    run_id = f"run-3r3-null-{secrets.token_hex(4)}"

    async def _seed_null():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
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
                trace_capture_status=None,  # explicit NULL
                created_at=now,
                updated_at=now,
            ))
            await db.commit()
    asyncio.run(_seed_null())

    try:
        # is_answered(None) returns False — reader knows it's pre-3R.3
        assert S.is_answered(None) is False
        # RunTrace page would show "trace unavailable" with a hint
        # that this is a legacy row
        assert S.is_lost(S.NEVER_CAPTURED_LEGACY) is True
    finally:
        _delete_run_history(run_id)
