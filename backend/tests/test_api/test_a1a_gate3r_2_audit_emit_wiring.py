"""Phase A1A Gate 3R.2 — Material audit emit wiring.

Charter §3R.2 carry-over: wire the audit emit sites that were declared
in the Gate 3.6 allowlist but had no actual emit code.

Actions covered (all tenant-scope, written via ``log_action``):

  run.cancel          — POST /api/v1/runs/{run_id}/cancel (any non-error outcome)
  run.complete        — agent_run endpoint final persist (response.error == False)
  run.failed          — agent_run endpoint final persist (response.error == True)
  idempotency.dedup   — agent_run endpoint dedup replay branch (should_run == False)
  api_client.rotate   — POST /api/clients/{client_id}/rotate

Actions explicitly DEFERRED or N/A:

  run.timeout         — DEFERRED. No agent-run timeout watchdog exists today
                        (the runtime_registry timeout checker is for state-
                        machine cases, not agent runs). The action remains
                        in the allowlist for future emit when a watchdog
                        is added.
  context.clear       — N/A per charter §3.6. Patient context clear is a
                        Phase 6 Gate 2 runtime/widget concept; the backend
                        has no DB row to audit.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── Helpers ────────────────────────────────────────────────────────


def _count_audit(action: str, resource_id: str | None = None) -> int:
    from app.database import AsyncSessionLocal
    async def _go() -> int:
        async with AsyncSessionLocal() as db:
            if resource_id is None:
                r = await db.execute(text(
                    "SELECT COUNT(*) FROM audit_logs WHERE action = :a"
                ), {"a": action})
            else:
                r = await db.execute(text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE action = :a AND resource_id = :rid"
                ), {"a": action, "rid": resource_id})
            return int(r.scalar() or 0)
    return asyncio.run(_go())


def _delete_audit(action: str, resource_id: str | None = None) -> None:
    from app.database import AsyncSessionLocal
    async def _go():
        async with AsyncSessionLocal() as db:
            if resource_id is None:
                await db.execute(text(
                    "DELETE FROM audit_logs WHERE action = :a"
                ), {"a": action})
            else:
                await db.execute(text(
                    "DELETE FROM audit_logs "
                    "WHERE action = :a AND resource_id = :rid"
                ), {"a": action, "rid": resource_id})
            await db.commit()
    asyncio.run(_go())


def _seed_pending_run(
    run_id: str,
    *,
    org_id: str = "org_default1",
    status: str = "PENDING",
) -> None:
    """Insert a PENDING run_history row directly so cancel_run has
    something to cancel without doing a full agent_run."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    async def _go():
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
                organization_id=org_id,
                tenancy_classification="MODERN",
                status=status,
                latency_ms=0,
                cost_usd=0.0,
                input_text="",
                output_summary="",
                error=False,
                created_at=now,
                updated_at=now,
            ))
            await db.commit()
    asyncio.run(_go())


def _clear_run_history(run_id: str) -> None:
    from app.database import AsyncSessionLocal
    async def _go():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            await db.commit()
    asyncio.run(_go())


# ── §1 run.cancel emits an audit row ──────────────────────────────


def test_run_cancel_emits_audit(client: TestClient) -> None:
    """POST /api/v1/runs/{run_id}/cancel emits a ``run.cancel`` audit
    row on the CANCELLED outcome."""
    run_id = f"run-3r2-cancel-{secrets.token_hex(4)}"
    _seed_pending_run(run_id)
    _delete_audit("run.cancel", run_id)
    try:
        before = _count_audit("run.cancel", run_id)
        resp = client.post(
            f"/api/v1/runs/{run_id}/cancel",
            json={"reason": "user-requested"},
        )
        assert resp.status_code == 200, resp.text
        after = _count_audit("run.cancel", run_id)
        assert after == before + 1, (
            f"run.cancel audit emit missing: before={before} after={after}"
        )
    finally:
        _delete_audit("run.cancel", run_id)
        _clear_run_history(run_id)


def test_running_cancel_is_202_recorded_only_and_audited(client: TestClient) -> None:
    """A provider call that cannot be interrupted is never reported as a
    successful synchronous cancellation."""
    run_id = f"run-3r2-running-{secrets.token_hex(4)}"
    _seed_pending_run(run_id, status="RUNNING")
    _delete_audit("run.cancel", run_id)
    try:
        resp = client.post(
            f"/api/v1/runs/{run_id}/cancel",
            json={"reason": "operator-requested"},
        )
        assert resp.status_code == 202, resp.text
        assert resp.json()["outcome"] == "RECORDED_ONLY"
        assert resp.json()["status"] == "CANCEL_NOT_SUPPORTED"
        status = client.get(f"/api/v1/runs/{run_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "CANCEL_NOT_SUPPORTED"
        assert status.json()["terminal"] is False
        assert _count_audit("run.cancel", run_id) == 1
    finally:
        _delete_audit("run.cancel", run_id)
        _clear_run_history(run_id)


def test_run_cancel_audit_carries_outcome(client: TestClient) -> None:
    """The audit details include the outcome so Security Admin can
    distinguish CANCELLED vs RECORDED_ONLY vs ALREADY_COMPLETE."""
    run_id = f"run-3r2-outcome-{secrets.token_hex(4)}"
    _seed_pending_run(run_id)
    _delete_audit("run.cancel", run_id)
    try:
        client.post(
            f"/api/v1/runs/{run_id}/cancel",
            json={"reason": "test"},
        )
        from app.database import AsyncSessionLocal
        async def _fetch():
            async with AsyncSessionLocal() as db:
                r = await db.execute(text(
                    "SELECT details FROM audit_logs "
                    "WHERE action = 'run.cancel' AND resource_id = :rid "
                    "ORDER BY created_at DESC LIMIT 1"
                ), {"rid": run_id})
                row = r.first()
                return row[0] if row else None
        details = asyncio.run(_fetch())
        assert details is not None
        assert "outcome" in details
        assert "status" in details
    finally:
        _delete_audit("run.cancel", run_id)
        _clear_run_history(run_id)


def test_run_cancel_not_found_does_not_emit(client: TestClient) -> None:
    """Cancel of a non-existent run → 404 → no audit emit (no
    successful cancel took place)."""
    run_id = f"run-3r2-notfound-{secrets.token_hex(4)}"
    _delete_audit("run.cancel", run_id)
    try:
        before = _count_audit("run.cancel", run_id)
        resp = client.post(f"/api/v1/runs/{run_id}/cancel", json={})
        assert resp.status_code == 404
        after = _count_audit("run.cancel", run_id)
        assert after == before, (
            f"run.cancel audit emit leaked on 404: before={before} after={after}"
        )
    finally:
        _delete_audit("run.cancel", run_id)


# ── §2 idempotency.dedup emits on replay ──────────────────────────


def test_idempotency_dedup_emits_on_replay(client: TestClient) -> None:
    """Two agent_run requests with the same Idempotency-Key produce
    one ``idempotency.dedup`` audit row (on the second request).

    Uses the smoke medical-coding agent (mock provider) to keep the
    test fast.
    """
    from app.services.idempotency_service import (
        compute_request_hash, acquire_or_replay, mark_completed,
        STATUS_COMPLETED,
    )
    from app.database import AsyncSessionLocal
    from app.models.idempotency_record import IdempotencyRecord

    key = f"test-3r2-key-{secrets.token_hex(4)}"
    agent_ref = "medical-coding-agent"
    request_hash = compute_request_hash(
        agent_id=agent_ref,
        input_text="test input for idempotency",
        runtime_mode="",
    )

    # First acquire (winner) — should NOT emit dedup.
    _delete_audit("idempotency.dedup")
    async def _first_acquire():
        async with AsyncSessionLocal() as db:
            result = await acquire_or_replay(
                db,
                idempotency_key=key,
                request_hash=request_hash,
                agent_ref=agent_ref,
                organization_id="org_default1",
                api_client_id="",
            )
            await db.commit()
            return result
    first = asyncio.run(_first_acquire())
    assert first.should_run is True
    before_winner = _count_audit("idempotency.dedup")
    assert before_winner == 0, "winner acquire must not emit dedup"

    # Mark the first record COMPLETED so the next call is a true replay.
    async def _mark():
        async with AsyncSessionLocal() as db:
            first.record.status = STATUS_COMPLETED
            first.record.run_id = f"run-{secrets.token_hex(4)}"
            first.record.response_snapshot = {"agent_id": agent_ref, "run_id": first.record.run_id}
            db.add(first.record)
            await db.commit()
    asyncio.run(_mark())

    # Second acquire (replay) — SHOULD emit dedup.
    async def _second_acquire():
        async with AsyncSessionLocal() as db:
            result = await acquire_or_replay(
                db,
                idempotency_key=key,
                request_hash=request_hash,
                agent_ref=agent_ref,
                organization_id="org_default1",
                api_client_id="",
            )
            await db.commit()
            return result
    second = asyncio.run(_second_acquire())
    assert second.should_run is False
    after_replay = _count_audit("idempotency.dedup")
    assert after_replay >= 1, (
        f"idempotency.dedup audit emit missing on replay: count={after_replay}"
    )

    # Cleanup
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM idempotency_records WHERE idempotency_key = :k"
            ), {"k": key})
            await db.commit()
    asyncio.run(_cleanup())
    _delete_audit("idempotency.dedup")


# ── §3 api_client.rotate emits ────────────────────────────────────


def test_api_client_rotate_emits_audit(client: TestClient) -> None:
    """POST /api/clients/{client_id}/rotate emits an
    ``api_client.rotate`` audit row."""
    # Create a client first (scopes as space-separated string per API)
    create_resp = client.post("/api/clients", json={
        "name": f"rotate-test-{secrets.token_hex(4)}",
        "scopes": "agents:run runs:read",
        "allowed_origins": ["https://example.com"],
    })
    assert create_resp.status_code in (200, 201), create_resp.text
    body = create_resp.json()
    client_id = body["client_id"]

    _delete_audit("api_client.rotate", client_id)
    try:
        before = _count_audit("api_client.rotate", client_id)
        resp = client.post(f"/api/clients/{client_id}/rotate")
        assert resp.status_code in (200, 201), resp.text
        after = _count_audit("api_client.rotate", client_id)
        assert after == before + 1, (
            f"api_client.rotate audit emit missing: before={before} after={after}"
        )
    finally:
        _delete_audit("api_client.rotate", client_id)
        # Disable the client to clean up
        try:
            client.post(f"/api/clients/{client_id}/disable")
        except Exception:
            pass


# ── §4 Allowlist invariants (regression) ──────────────────────────


def test_run_lifecycle_actions_in_allowlist() -> None:
    """Gate 3R.2 wiring depends on the actions being in the allowlist.
    Asserting presence prevents accidental removal in future
    refactors."""
    from app.services.system_audit import ALL_SYSTEM_AUDIT_ACTIONS
    for action in (
        "run.cancel",
        "run.timeout",
        "run.complete",
        "run.failed",
        "idempotency.dedup",
        "api_client.rotate",
        "context.clear",
    ):
        assert action in ALL_SYSTEM_AUDIT_ACTIONS, (
            f"{action!r} missing from ALL_SYSTEM_AUDIT_ACTIONS"
        )


def test_legacy_classifier_recognizes_lifecycle_actions() -> None:
    """The classifier must recognise the lifecycle actions so they
    classify as MODERN (with org) or MODERN_SYSTEM (without)."""
    from app.services.legacy_tenancy_attribution import SYSTEM_AUDIT_ACTIONS
    for action in (
        "run.cancel",
        "run.timeout",
        "run.complete",
        "run.failed",
        "idempotency.dedup",
        "api_client.rotate",
        "context.clear",
    ):
        assert action in SYSTEM_AUDIT_ACTIONS, (
            f"{action!r} missing from SYSTEM_AUDIT_ACTIONS"
        )
