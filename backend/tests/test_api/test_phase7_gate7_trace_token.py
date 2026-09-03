"""Phase 7 Gate 7 §12 — Partner-secured Trace URL tests.

Covers:
  - Trace token issuance produces a non-empty URL with ?token=...
  - Token verification succeeds for fresh token + matching run_id
  - Token verification fails for tampered signature
  - Token verification fails for wrong run_id
  - Token verification fails for expired token
  - GET /api/v1/runs/{run_id}/trace without token → 401 TRACE_TOKEN_REQUIRED
  - GET /api/v1/runs/{run_id}/trace with valid token → 200 timeline
  - GET /api/v1/runs/{run_id}/trace with bad signature → 401 TRACE_TOKEN_INVALID
  - GET /api/v1/runs/{run_id}/trace with mismatched run_id → 401 TRACE_TOKEN_RUN_MISMATCH
"""
from __future__ import annotations

import os
import time

import pytest
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
# §12.1 trace_token service unit tests
# ────────────────────────────────────────────────────────────────────


def test_issue_trace_token_returns_nonempty_string() -> None:
    from app.services.trace_token import issue_trace_token
    token = issue_trace_token(run_id="run-abc")
    assert isinstance(token, str)
    assert "." in token
    payload_b64, sig = token.rsplit(".", 1)
    assert len(payload_b64) > 0
    assert len(sig) > 0


def test_verify_fresh_token_with_matching_run_id_succeeds() -> None:
    from app.services.trace_token import issue_trace_token, verify_trace_token
    token = issue_trace_token(run_id="run-abc", organization_id="org-1")
    claims = verify_trace_token(token, expected_run_id="run-abc")
    assert claims.run_id == "run-abc"
    assert claims.organization_id == "org-1"
    assert claims.exp > int(time.time())


def test_verify_token_with_tampered_signature_fails() -> None:
    from app.services.trace_token import (
        TraceTokenInvalidSignature,
        issue_trace_token,
        verify_trace_token,
    )
    token = issue_trace_token(run_id="run-abc")
    payload_b64, _ = token.rsplit(".", 1)
    # Flip one character of the signature to break it.
    bad_sig = "A" + "B" * 40
    bad_token = f"{payload_b64}.{bad_sig}"
    with pytest.raises(TraceTokenInvalidSignature):
        verify_trace_token(bad_token, expected_run_id="run-abc")


def test_verify_token_with_wrong_run_id_fails() -> None:
    from app.services.trace_token import (
        TraceTokenRunMismatch,
        issue_trace_token,
        verify_trace_token,
    )
    token = issue_trace_token(run_id="run-abc")
    with pytest.raises(TraceTokenRunMismatch):
        verify_trace_token(token, expected_run_id="run-XYZ")


def test_verify_expired_token_fails() -> None:
    from app.services.trace_token import (
        TraceTokenExpired,
        issue_trace_token,
        verify_trace_token,
    )
    token = issue_trace_token(run_id="run-abc", ttl_seconds=-10)
    with pytest.raises(TraceTokenExpired):
        verify_trace_token(token, expected_run_id="run-abc")


def test_verify_malformed_token_fails() -> None:
    from app.services.trace_token import (
        TraceTokenMalformed,
        verify_trace_token,
    )
    with pytest.raises(TraceTokenMalformed):
        verify_trace_token("not-a-real-token", expected_run_id="run-abc")


def test_build_trace_url_includes_base_run_and_token() -> None:
    from app.services.trace_token import build_trace_url, verify_trace_token
    url = build_trace_url(
        "https://api.icoder.cloud",
        run_id="run-abc",
        organization_id="org-1",
        api_client_id="partner-1",
    )
    assert url.startswith("https://api.icoder.cloud/api/v1/runs/run-abc/trace?token=")
    token = url.split("token=", 1)[1]
    claims = verify_trace_token(token, expected_run_id="run-abc")
    assert claims.run_id == "run-abc"
    assert claims.organization_id == "org-1"
    assert claims.api_client_id == "partner-1"


# ────────────────────────────────────────────────────────────────────
# §12.2 GET /api/v1/runs/{run_id}/trace endpoint tests
# ────────────────────────────────────────────────────────────────────


def test_get_trace_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/run-abc/trace")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TRACE_TOKEN_REQUIRED"


def test_get_trace_with_valid_token_returns_timeline(
    client: TestClient, tmp_path
) -> None:
    """Seed an in-memory RunTraceStore, issue a token, verify the timeline."""
    import asyncio
    import secrets as _secrets
    from datetime import datetime, UTC
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, get_default_store,
    )
    from app.services.trace_token import issue_trace_token

    # Phase A1A Gate 3R.1 — seed an authoritative run_history row so
    # the partner trace endpoint doesn't refuse on orphan-run grounds.
    async def _seed_row():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = 'run-abc'"
            ))
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=_secrets.token_hex(6),
                run_id="run-abc",
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
    asyncio.run(_seed_row())

    # Use the process-default store (in-memory in test mode). Clear
    # first so we don't pick up events from earlier tests.
    store = get_default_store()
    store.clear()
    store.append(RunTraceEvent(
        run_id="run-abc", step="ingest", status="ok",
        ts=time.time(), duration_ms=10,
    ))

    try:
        token = issue_trace_token(run_id="run-abc")
        resp = client.get(f"/api/v1/runs/run-abc/trace?token={token}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["run_id"] == "run-abc"
        assert body["step_count"] == 1
        assert body["timeline"][0]["step"] == "ingest"
        assert body["trace_token"]["exp"] > int(time.time())
    finally:
        store.clear()  # don't leak to other tests
        async def _clear_row():
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    "DELETE FROM run_history WHERE run_id = 'run-abc'"
                ))
                await db.commit()
        asyncio.run(_clear_row())


def test_get_trace_with_invalid_signature_returns_401(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/runs/run-abc/trace?token=AAAAA.BBBBB"
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] in ("TRACE_TOKEN_INVALID", "TRACE_TOKEN_MALFORMED")


def test_get_trace_with_run_mismatch_returns_401(client: TestClient) -> None:
    from app.services.trace_token import issue_trace_token
    token = issue_trace_token(run_id="run-abc")
    resp = client.get(f"/api/v1/runs/run-XYZ/trace?token={token}")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TRACE_TOKEN_RUN_MISMATCH"


def test_get_trace_with_expired_token_returns_401(client: TestClient) -> None:
    from app.services.trace_token import issue_trace_token
    token = issue_trace_token(run_id="run-abc", ttl_seconds=-100)
    resp = client.get(f"/api/v1/runs/run-abc/trace?token={token}")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TRACE_TOKEN_EXPIRED"


def test_get_trace_run_not_found_returns_404(client: TestClient) -> None:
    """Token is valid but the run has no trace events (never ran)."""
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    from app.services.trace_token import issue_trace_token

    # Clear the store so the run_id definitely has no events.
    store = get_default_store()
    store.clear()

    token = issue_trace_token(run_id="run-never-existed")
    resp = client.get(f"/api/v1/runs/run-never-existed/trace?token={token}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRACE_NOT_FOUND"
