"""Phase 4-G (2026-07-10) — Live cost + API Client + RunHistory tests.

Verifies the three P0 gaps closed in Phase 4-G #1-#3:

  #1 — Live cost backend wiring:
       - DeepSeekProvider/OpenAICompatibleProvider populate `cost_usd` in
         the generate() result dict (token usage × pricing)
       - AgentRunResponse.cost.amount flows through to the client

  #2 — API Client selector real binding:
       - POST /api/v1/agents/{id}/run accepts `api_client_id` in the body
       - The non-medical path emits trace metadata that records the
         `api_client_id` used (so /runs/{run_id}/trace surfaces it)

  #3 — RunHistory server-side persistence:
       - Each run writes one row to the run_history table
       - GET /api/runtime/runs/history returns recent runs (newest first)
       - Filter by agent_id narrows the list
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "phase4f_smoke"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── #1 — cost field shape on the non-medical-coding path ────────────────


def test_g1_cost_field_present_in_unified_response(client: TestClient) -> None:
    """AgentRunResponse.cost must be a dict (even if amount=0 under mock LLM).

    The backend computes cost_usd from token usage × pricing. Under
    LLM_PROVIDER=mock, MockLLMProvider returns zero tokens → cost={}.
    The shape is what matters here (amount population is exercised by
    `test_llm_cost_computation.py`).
    """
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["cost"], dict), (
        f"cost must be a dict (Phase 4-G #1 wiring), got: {type(data['cost'])}"
    )
    # When populated, cost has shape {"amount": float, "currency": "USD"}
    if data["cost"]:
        assert "amount" in data["cost"]
        assert "currency" in data["cost"]


# ── #2 — api_client_id is accepted and recorded in trace metadata ─────────


def test_g2_api_client_id_accepted_in_request_body(client: TestClient) -> None:
    """The unified endpoint must accept `api_client_id` without erroring."""
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {"text": fix["input_text"]},
            "api_client_id": "test-client-001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is False, f"unexpected error: {data.get('error_reason')}"


def test_g2_api_client_id_recorded_in_trace_metadata(client: TestClient) -> None:
    """api_client_id must surface in the user_message_received trace event.

    Evidence: GET /api/runtime/runs/{run_id}/trace returns trace_events;
    the first event's metadata must include `api_client_id`.
    """
    fix = _load_fixture("coding_evidence_case.json")
    test_client_id = "test-client-trace-001"
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {"text": fix["input_text"]},
            "api_client_id": test_client_id,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    run_id = data["run_id"]

    # Trace events in response envelope
    inline_events = data.get("trace_events", [])
    user_msg_events = [
        ev for ev in inline_events
        if ev.get("step") == "user_message_received"
    ]
    assert user_msg_events, (
        "no user_message_received event in trace_events; "
        f"got: {[ev.get('step') for ev in inline_events]}"
    )
    metadata = user_msg_events[0].get("metadata", {})
    assert metadata.get("api_client_id") == test_client_id, (
        f"api_client_id missing/wrong in trace metadata: {metadata}"
    )

    # Persisted trace retrievable by run_id
    trace_resp = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    # RunTrace endpoint returns events under either `timeline` or `events`
    persisted_events = (
        trace_data.get("timeline")
        or trace_data.get("events")
        or trace_data.get("trace_events")
        or []
    )
    persisted_user_msg = [
        ev for ev in persisted_events
        if ev.get("step") == "user_message_received"
    ]
    assert persisted_user_msg, (
        "no user_message_received event in persisted trace; "
        f"got: {[ev.get('step') for ev in persisted_events]}"
    )
    # RunTraceEvent.to_dict() surfaces metadata under `safe_metadata`
    # (the inline envelope uses `metadata`; persisted trace uses `safe_metadata`).
    persisted_metadata = (
        persisted_user_msg[0].get("safe_metadata")
        or persisted_user_msg[0].get("metadata")
        or {}
    )
    assert persisted_metadata.get("api_client_id") == test_client_id, (
        f"api_client_id missing in persisted trace: {persisted_metadata}"
    )


def test_g2_no_api_client_id_yields_empty_string_in_trace(
    client: TestClient,
) -> None:
    """When api_client_id is omitted, trace metadata records empty string (not None)."""
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    assert resp.status_code == 200
    data = resp.json()
    inline_events = data.get("trace_events", [])
    user_msg_events = [
        ev for ev in inline_events
        if ev.get("step") == "user_message_received"
    ]
    assert user_msg_events
    metadata = user_msg_events[0].get("metadata", {})
    assert metadata.get("api_client_id") == "", (
        f"expected empty string for missing api_client_id, got: {metadata.get('api_client_id')!r}"
    )


# ── #3 — RunHistory server-side persistence ─────────────────────────────


def test_g3_run_writes_to_run_history_table(client: TestClient) -> None:
    """Each unified run writes a row to the run_history table.

    Evidence: after a successful run, GET /api/runtime/runs/history?agent_id=X
    returns the run_id we just executed.
    """
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # Wait for the sync DB write to commit (it's synchronous in agent_run.py).
    hist_resp = client.get(
        "/api/runtime/runs/history",
        params={"agent_id": fix["agent_id"], "limit": 50},
    )
    assert hist_resp.status_code == 200, (
        f"GET /runs/history returned {hist_resp.status_code}: {hist_resp.text[:300]}"
    )
    payload = hist_resp.json()
    items = payload.get("items", [])
    assert isinstance(items, list)
    matching = [it for it in items if it.get("run_id") == run_id]
    assert matching, (
        f"run_id {run_id} not in run_history; got {[it.get('run_id') for it in items]}"
    )
    row = matching[0]
    # Row shape contract — fields the frontend hydration relies on.
    assert row["agent_id"] == fix["agent_id"]
    assert isinstance(row["latency_ms"], int)
    assert isinstance(row["cost_usd"], (int, float))
    assert row.get("input_preview")  # input_text truncated to 200 chars
    assert row.get("created_at")  # ISO timestamp for ordering
    assert "error" in row  # bool flag


def test_g3_history_filtered_by_agent_id(client: TestClient) -> None:
    """Filtering by agent_id narrows the list to that agent's runs only."""
    fix1 = _load_fixture("coding_evidence_case.json")  # evidence-extractor
    fix2 = _load_fixture("discharge_summary_case.json")  # discharge-summary-structuring
    # Run each agent once.
    r1 = client.post(
        f"/api/v1/agents/{fix1['agent_id']}/run",
        json={"input": {"text": fix1["input_text"]}},
    )
    r2 = client.post(
        f"/api/v1/agents/{fix2['agent_id']}/run",
        json={"input": {"text": fix2["input_text"]}},
    )
    assert r1.status_code == 200 and r2.status_code == 200

    # Filter by agent_id = evidence-extractor — should NOT include discharge.
    hist_resp = client.get(
        "/api/runtime/runs/history",
        params={"agent_id": fix1["agent_id"], "limit": 50},
    )
    assert hist_resp.status_code == 200
    items = hist_resp.json().get("items", [])
    assert items, "expected at least one history row for evidence-extractor"
    agent_ids = {it["agent_id"] for it in items}
    assert agent_ids == {fix1["agent_id"]}, (
        f"filter by agent_id leaked other agents: {agent_ids}"
    )


def test_g3_history_ordered_newest_first(client: TestClient) -> None:
    """Runs are ordered by created_at desc so the dropdown shows recent runs on top."""
    fix = _load_fixture("coding_evidence_case.json")
    # Run twice to get two rows in chronological order.
    r1 = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    run_id_1 = r1.json()["run_id"]
    r2 = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    run_id_2 = r2.json()["run_id"]
    assert r1.status_code == 200 and r2.status_code == 200

    hist_resp = client.get(
        "/api/runtime/runs/history",
        params={"agent_id": fix["agent_id"], "limit": 50},
    )
    assert hist_resp.status_code == 200
    items = hist_resp.json().get("items", [])
    run_ids = [it["run_id"] for it in items]
    # Newest (run_id_2) must come before oldest (run_id_1).
    if run_id_2 in run_ids and run_id_1 in run_ids:
        assert run_ids.index(run_id_2) < run_ids.index(run_id_1), (
            f"expected newest first; got order: {run_ids}"
        )
