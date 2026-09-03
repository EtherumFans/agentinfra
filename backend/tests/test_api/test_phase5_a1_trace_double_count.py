"""Phase 5 A1 — Trace step duration double-count regression test (BUG-12-01).

Context (per Phase 4-H §12 audit):
  Before A1 fix, _run_via_provider_registry() emitted USER_MESSAGE_RECEIVED,
  OUTPUT_GENERATED, COMPLETION directly to RunTraceStore AND
  _map_backend_response() built inline trace_events with the same 3 steps,
  AND persist_trace_events() re-emitted the inline events to RunTraceStore.
  Result: 6 events in RunTraceStore for a 3-step run (each step appeared
  twice — once without duration from the direct emit, once with duration
  from persist_trace_events).

Fix (A1, 2026-07-10):
  - _run_via_provider_registry() keeps only USER_MESSAGE_RECEIVED direct
    emit (line 538) for the success path. OUTPUT_GENERATED + COMPLETION
    direct emits are removed.
  - _map_backend_response() inline trace_events omits user_message_received
    (since line 538 already emits it directly). Inline has only
    OUTPUT_GENERATED + COMPLETION.
  - persist_trace_events() re-emits the 2 inline events on success path.
  - Error paths keep direct COMPLETION failed emit (lines 553/574/626).

Expected trace counts after fix:
  - Provider response (success or fail-closed): 3 events
    (USER_MESSAGE_RECEIVED + OUTPUT_GENERATED + COMPLETION)
  - Provider response that fails the output contract: 4 events, adding the
    explicit CONTRACT_VALIDATION failure event before COMPLETION.
  - Error path (unknown_agent): 2 events (USER_MESSAGE_RECEIVED + COMPLETION failed)
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
    with open(_FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_a1_provider_path_has_no_duplicate_trace_events(
    client: TestClient,
) -> None:
    """A1 regression: provider-path run must produce exactly 3 trace events.

    Before fix: 6 events (each of USER_MESSAGE_RECEIVED, OUTPUT_GENERATED,
    COMPLETION appeared twice — once without duration from direct emit,
    once with duration from persist_trace_events).
    After fix: the three lifecycle events appear exactly once; a contract
    violation may add one explicit contract_validation event.
    """
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
            "include_trace": True,
        },
    )
    assert resp.status_code == 200, (
        f"run failed: {resp.status_code} {resp.text[:300]}"
    )
    body = resp.json()
    # Evidence Extractor is a governed local exact-mention Provider and does
    # not depend on the configured mock LLM. Its successful trace must still
    # contain each lifecycle event exactly once.
    assert body.get("error") is False
    assert body["result"]["extraction_status"] == "COMPLETED"
    run_id = body["run_id"]

    trace_resp = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace_resp.status_code == 200
    timeline = trace_resp.json().get("timeline", trace_resp.json().get("events", []))

    # Bug-12-01: no duplicate lifecycle events. The local Provider produces a
    # contract-valid result, so only the three lifecycle events are expected.
    assert len(timeline) == 3, (
        f"BUG-12-01 regression: expected exactly 3 trace events for a valid "
        f"provider path, got {len(timeline)}. "
        f"Steps: {[ev.get('step') for ev in timeline]}"
    )

    # Each step must appear exactly once.
    steps = [ev.get("step") for ev in timeline]
    assert steps.count("user_message_received") == 1, (
        f"USER_MESSAGE_RECEIVED must appear exactly once, got {steps.count('user_message_received')}"
    )
    assert steps.count("output_generated") == 1, (
        f"OUTPUT_GENERATED must appear exactly once, got {steps.count('output_generated')}"
    )
    assert steps.count("completion") == 1, (
        f"COMPLETION must appear exactly once, got {steps.count('completion')}"
    )
    assert steps.count("contract_validation") == 0
    completion_ev = next(ev for ev in timeline if ev.get("step") == "completion")
    assert completion_ev.get("status") == "ok"


def test_a1_error_path_has_exactly_2_trace_events_no_double_count(
    client: TestClient,
) -> None:
    """A1 regression: error-path run must produce exactly 2 trace events.

    Before fix: 2 events (USER_MESSAGE_RECEIVED direct + COMPLETION failed direct).
    After fix: same 2 events (no double-emit because persist_trace_events is
    skipped on error path).
    """
    # Trigger an unknown_agent error.
    resp = client.post(
        "/api/v1/agents/nonexistent-p0-agent-xyz/run",
        json={
            "input": {"text": "test input"},
            "include_trace": True,
        },
    )
    assert resp.status_code == 200  # structured error returns 200 with error=true
    body = resp.json()
    assert body.get("error") is True, f"expected error=true, got: {body}"
    run_id = body["run_id"]

    trace_resp = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace_resp.status_code == 200
    timeline = trace_resp.json().get("timeline", trace_resp.json().get("events", []))

    # Must be exactly 2 (USER_MESSAGE_RECEIVED + COMPLETION failed).
    assert len(timeline) == 2, (
        f"BUG-12-01 regression on error path: expected exactly 2 trace events "
        f"(USER_MESSAGE_RECEIVED + COMPLETION failed), got {len(timeline)}. "
        f"Steps: {[ev.get('step') for ev in timeline]}"
    )

    steps = [ev.get("step") for ev in timeline]
    assert steps.count("user_message_received") == 1
    assert steps.count("completion") == 1
    # COMPLETION must be failed status.
    completion_ev = next(ev for ev in timeline if ev.get("step") == "completion")
    assert completion_ev.get("status") == "failed", (
        f"error-path COMPLETION must be status=failed, got {completion_ev.get('status')}"
    )
