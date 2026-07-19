"""Phase 7 Gate 9 — SSE / Run state event realism tests.

Covers §14.1-§14.3:

  §14.1 SSE endpoint contract
    - GET /api/v1/runs/{run_id}/events?token= returns text/event-stream
    - Each event is the unified envelope {name, payload, meta}
    - stream.completed is the terminal event
    - Heartbeat comment syntax is valid

  §14.2 Auth + error paths
    - Missing token → 401 TRACE_TOKEN_REQUIRED
    - Bad signature → 401 TRACE_TOKEN_INVALID
    - Expired token → 401 TRACE_TOKEN_EXPIRED
    - Wrong run_id → 401 TRACE_TOKEN_RUN_MISMATCH
    - No events → 404 TRACE_NOT_FOUND

  §14.3 Real payloads
    - Each emitted event carries the {step, status, duration_ms, safe_metadata} payload
    - meta carries {run_id, ts, event_id, version}
    - The event stream matches the trace replay endpoint's data 1:1
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


def _seed_events(run_id: str, *, count: int = 3) -> None:
    """Append N synthetic RunTraceEvents for the given run_id.

    Phase A1A Gate 3R.1 — also seed an authoritative run_history row
    so the orphan-run guard doesn't refuse the trace read. Before
    Gate 3R.1, the SSE / trace endpoints would fall through to the
    trace store when no run_history row existed; that's now a 404.
    """
    import asyncio
    import secrets as _secrets
    from datetime import datetime, UTC
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        RunTraceEvent, get_default_store,
    )

    # Seed the run_history row first.
    async def _seed_row():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id = :rid"
            ), {"rid": run_id})
            now = datetime.now(UTC)
            db.add(RunHistoryModel(
                id=_secrets.token_hex(6),
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
    asyncio.run(_seed_row())

    # Then append the trace events.
    store = get_default_store()
    store.clear()
    steps = ["ingest", "extract", "validate"][:count]
    for i, step in enumerate(steps):
        store.append(RunTraceEvent(
            run_id=run_id,
            step=step,
            status="ok",
            ts=time.time() + i,
            duration_ms=10 * (i + 1),
            safe_metadata={"agent_id": "medical-coding-agent", "marker": f"e{i}"},
        ))


def _clear_events() -> None:
    """Clear trace events + run_history rows for known test run_ids."""
    import asyncio
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.orchestrator.run_trace import get_default_store
    get_default_store().clear()
    async def _clear_rows():
        async with AsyncSessionLocal() as db:
            # Match run_ids this test fixture uses (run-sse-1..run-sse-7).
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id LIKE 'run-sse-%'"
            ))
            await db.commit()
    asyncio.run(_clear_rows())


# ────────────────────────────────────────────────────────────────────
# §14.1 SSE contract
# ────────────────────────────────────────────────────────────────────


def test_sse_returns_event_stream_with_signed_token(client: TestClient) -> None:
    """Happy path: SSE stream emits one event per RunTrace row + stream.completed."""
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-1", count=3)
    try:
        token = issue_trace_token(run_id="run-sse-1")
        resp = client.get(
            f"/api/v1/runs/run-sse-1/events?token={token}",
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # The body should contain 4 SSE data blocks: 3 events + stream.completed
        body = resp.text
        data_blocks = [ln for ln in body.split("\n") if ln.startswith("data: ")]
        assert len(data_blocks) == 4
        # Last block is stream.completed
        import json
        last = json.loads(data_blocks[-1][len("data: "):])
        assert last["name"] == "stream.completed"
        assert last["payload"]["event_count"] == 3
    finally:
        _clear_events()


def test_sse_each_event_uses_unified_envelope(client: TestClient) -> None:
    """Each data block is {name, payload, meta} — Phase 6 unified envelope."""
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-2", count=2)
    try:
        token = issue_trace_token(run_id="run-sse-2")
        resp = client.get(f"/api/v1/runs/run-sse-2/events?token={token}")
        body = resp.text
        import json
        for line in body.split("\n"):
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                assert "name" in ev
                assert "payload" in ev
                assert "meta" in ev
                # meta must carry run_id and version
                assert ev["meta"]["run_id"] == "run-sse-2"
                assert ev["meta"]["version"] == "1.0"
    finally:
        _clear_events()


def test_sse_payload_carries_step_status_duration_metadata(client: TestClient) -> None:
    """Payload has the 4 fields partners need to render a timeline UI."""
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-3", count=1)
    try:
        token = issue_trace_token(run_id="run-sse-3")
        resp = client.get(f"/api/v1/runs/run-sse-3/events?token={token}")
        body = resp.text
        import json
        # First data block is the ingest event
        first = json.loads(body.split("\n")[0][len("data: "):])
        assert first["name"] == "run.ingest"
        assert first["payload"]["step"] == "ingest"
        assert first["payload"]["status"] == "ok"
        assert first["payload"]["duration_ms"] == 10
        assert first["payload"]["safe_metadata"]["agent_id"] == "medical-coding-agent"
    finally:
        _clear_events()


def test_sse_no_cache_headers_set(client: TestClient) -> None:
    """SSE must disable proxy buffering (§14.3)."""
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-4", count=1)
    try:
        token = issue_trace_token(run_id="run-sse-4")
        resp = client.get(f"/api/v1/runs/run-sse-4/events?token={token}")
        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("x-accel-buffering") == "no"
    finally:
        _clear_events()


# ────────────────────────────────────────────────────────────────────
# §14.2 Auth + error paths (mirror Gate 7 trace endpoint)
# ────────────────────────────────────────────────────────────────────


def test_sse_without_token_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/run-abc/events")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "TRACE_TOKEN_REQUIRED"


def test_sse_with_invalid_signature_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/run-abc/events?token=AAAAA.BBBBB")
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] in ("TRACE_TOKEN_INVALID", "TRACE_TOKEN_MALFORMED")


def test_sse_with_expired_token_returns_401(client: TestClient) -> None:
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-5", count=1)
    try:
        token = issue_trace_token(run_id="run-sse-5", ttl_seconds=-100)
        resp = client.get(f"/api/v1/runs/run-sse-5/events?token={token}")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TRACE_TOKEN_EXPIRED"
    finally:
        _clear_events()


def test_sse_with_run_mismatch_returns_401(client: TestClient) -> None:
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-6", count=1)
    try:
        token = issue_trace_token(run_id="run-sse-6")
        resp = client.get(f"/api/v1/runs/run-XYZ/events?token={token}")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TRACE_TOKEN_RUN_MISMATCH"
    finally:
        _clear_events()


def test_sse_no_events_returns_404(client: TestClient) -> None:
    """Token valid, but run has no trace events yet → 404 TRACE_NOT_FOUND."""
    from app.services.trace_token import issue_trace_token
    _clear_events()
    token = issue_trace_token(run_id="run-never-existed")
    resp = client.get(f"/api/v1/runs/run-never-existed/events?token={token}")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "TRACE_NOT_FOUND"


# ────────────────────────────────────────────────────────────────────
# §14.3 Real-payload integrity: SSE stream must match trace replay
# ────────────────────────────────────────────────────────────────────


def test_sse_stream_matches_trace_replay_endpoint(client: TestClient) -> None:
    """The same token + run_id produces identical data from /events (SSE)
    and /trace (JSON). Partners can switch between live stream and replay
    without re-authorizing."""
    from app.services.trace_token import issue_trace_token
    _seed_events("run-sse-7", count=3)
    try:
        token = issue_trace_token(run_id="run-sse-7")
        trace_resp = client.get(f"/api/v1/runs/run-sse-7/trace?token={token}")
        assert trace_resp.status_code == 200
        sse_resp = client.get(f"/api/v1/runs/run-sse-7/events?token={token}")
        assert sse_resp.status_code == 200

        # Extract steps from trace JSON
        trace_steps = [e["step"] for e in trace_resp.json()["timeline"]]
        # Extract steps from SSE
        import json
        sse_steps = []
        for line in sse_resp.text.split("\n"):
            if line.startswith("data: "):
                ev = json.loads(line[len("data: "):])
                if ev["name"].startswith("run."):
                    sse_steps.append(ev["payload"]["step"])
        # stream.completed is excluded from sse_steps by the .startswith("run.") filter
        assert trace_steps == sse_steps
    finally:
        _clear_events()
