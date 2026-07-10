"""Phase 4-F3 (2026-07-10) — Core Agent Smoke Runs (non-Medical-Coding).

Tests the 9 requirements per prompt §7 — 4 P0 non-Medical-Coding agents
(evidence-extractor, principal-diagnosis-review, drg-analyzer,
discharge-summary-structuring) run stably via the A2A-compatible
unified Agent Run endpoint and produce structured envelopes.

Architecture (§2):
  - All 4 agents route through ProviderRegistry → PureLLMProvider.
  - Under LLM_PROVIDER=mock, MockLLMProvider returns a deterministic
    generic JSON (doesn't match each agent's output_contract, but
    exercises the full envelope construction + trace persistence path).
  - Tests assert envelope structure (13 fields, run_id, trace_id,
    runtime_mode=a2a_pure_llm, latency_ms < 30000, trace_events
    persisted and retrievable). Tests do NOT assert specific output
    field shapes — those are validated by agent_pack.json schema
    validation and will be exercised by real DeepSeek in browser
    walkthrough (§9).

Browser walkthrough (§9) covers real-DeepSeek output shape parity.
"""
from __future__ import annotations

import json
import os
import time
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


# The 4 P0 non-Medical-Coding agents per prompt §2.1.
P0_AGENTS = [
    ("evidence-extractor", "coding_evidence_case.json"),
    ("principal-diagnosis-review", "principal_dx_review_case.json"),
    ("drg-analyzer", "drg_dip_risk_case.json"),
    ("discharge-summary-structuring", "discharge_summary_case.json"),
]


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── §7 #1-4: each P0 agent returns a 200 with structured envelope ──────


def _assert_envelope_shape(data: dict, agent_id: str, fix: dict) -> None:
    """Assert the 13-field envelope shape per prompt §9.1."""
    # Envelope IDs
    assert data["agent_id"] == agent_id, f"agent_id mismatch: {data.get('agent_id')}"
    assert data["run_id"].startswith("run-"), (
        f"run_id not envelope-format: {data.get('run_id')}"
    )
    assert data["trace_id"].startswith("trace-"), (
        f"trace_id not envelope-format: {data.get('trace_id')}"
    )
    # 13-field envelope
    for field in ("agent_id", "run_id", "trace_id", "runtime_mode", "latency_ms",
                  "cost", "summary", "result", "evidence", "warnings",
                  "manual_review_required", "trace_events", "error", "error_reason"):
        assert field in data, f"missing envelope field: {field}"
    # No error
    assert data["error"] is False, (
        f"error=True for {agent_id}: reason={data.get('error_reason')}; "
        f"summary={data.get('summary')}"
    )


def test_f3_1_evidence_extractor_returns_structured_envelope(client: TestClient) -> None:
    """§7 #1: evidence-extractor POST /api/v1/agents/evidence-extractor/run → 200."""
    fix = _load_fixture("coding_evidence_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    _assert_envelope_shape(data, "evidence-extractor", fix)


def test_f3_2_principal_diagnosis_review_returns_structured_envelope(
    client: TestClient,
) -> None:
    """§7 #2: principal-diagnosis-review → 200 with structured envelope."""
    fix = _load_fixture("principal_dx_review_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    _assert_envelope_shape(data, "principal-diagnosis-review", fix)


def test_f3_3_drg_analyzer_returns_structured_envelope(client: TestClient) -> None:
    """§7 #3: drg-analyzer → 200 with structured envelope."""
    fix = _load_fixture("drg_dip_risk_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    _assert_envelope_shape(data, "drg-analyzer", fix)


def test_f3_4_discharge_summary_structuring_returns_structured_envelope(
    client: TestClient,
) -> None:
    """§7 #4: discharge-summary-structuring → 200 with structured envelope."""
    fix = _load_fixture("discharge_summary_case.json")
    resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={"input": {"text": fix["input_text"]}},
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    _assert_envelope_shape(data, "discharge-summary-structuring", fix)


# ── §7 #5: runtime_mode = a2a_pure_llm for all 4 P0 agents ─────────────


@pytest.mark.parametrize("agent_id,fixture_name", P0_AGENTS)
def test_f3_5_runtime_mode_is_a2a_pure_llm(
    client: TestClient, agent_id: str, fixture_name: str,
) -> None:
    """§7 #5: runtime_mode reflects each agent's default_runtime_mode.

    All 4 P0 packs declare ``default_runtime_mode = "a2a_pure_llm"`` —
    the response.runtime_mode must match.
    """
    fix = _load_fixture(fixture_name)
    resp = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["runtime_mode"] == "a2a_pure_llm", (
        f"{agent_id}: runtime_mode should be 'a2a_pure_llm', "
        f"got: {data['runtime_mode']}"
    )


# ── §7 #6: latency_ms < 30000 (mock gateway is instant) ─────────────────


@pytest.mark.parametrize("agent_id,fixture_name", P0_AGENTS)
def test_f3_6_latency_under_30s(
    client: TestClient, agent_id: str, fixture_name: str,
) -> None:
    """§7 #6: latency_ms < 30000 for all 4 P0 agents.

    Under MockLLMProvider the call is near-instant. The 30s ceiling
    matches the fixture's ``expected_latency_ms_max``.
    """
    fix = _load_fixture(fixture_name)
    t0 = time.perf_counter()
    resp = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
        },
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    data = resp.json()
    assert data["latency_ms"] < 30000, (
        f"{agent_id}: latency_ms={data['latency_ms']} > 30000 "
        f"(wall clock {elapsed_ms:.0f}ms)"
    )


# ── §7 #7: trace_events persisted and retrievable ───────────────────────


def test_f3_7_trace_events_persisted_and_retrievable(client: TestClient) -> None:
    """§7 #7: POST .../run then GET /api/runtime/runs/{run_id}/trace → 200.

    Non-medical-coding agents go through _run_via_provider_registry which
    emits 3 lifecycle trace events (USER_MESSAGE_RECEIVED, OUTPUT_GENERATED,
    COMPLETION). The unified endpoint then persists them to RunTraceStore
    via persist_trace_events(), so GET /api/runtime/runs/{run_id}/trace
    must return 200 with a non-empty timeline.
    """
    fix = _load_fixture("coding_evidence_case.json")
    run_resp = client.post(
        f"/api/v1/agents/{fix['agent_id']}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
            "include_trace": True,
        },
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    run_id = run_data["run_id"]
    inline_events = run_data.get("trace_events", [])
    # Expect 3 lifecycle events from _map_backend_response.
    assert len(inline_events) >= 1, (
        f"expected at least 1 inline trace_event for {fix['agent_id']}, got 0"
    )

    trace_resp = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace_resp.status_code == 200, (
        f"RunTrace endpoint returned {trace_resp.status_code}: {trace_resp.text[:300]}"
    )
    trace_data = trace_resp.json()
    timeline = trace_data.get("timeline", trace_data.get("events", []))
    assert len(timeline) >= 1, (
        f"RunTrace store empty for run_id={run_id} despite inline events"
    )


# ── §7 #8: 4 P0 agents all have retrievable trace ──────────────────────


@pytest.mark.parametrize("agent_id,fixture_name", P0_AGENTS)
def test_f3_8_trace_retrievable_for_all_p0_agents(
    client: TestClient, agent_id: str, fixture_name: str,
) -> None:
    """§7 #8: every P0 non-medical-coding agent has GET .../trace returning 200."""
    fix = _load_fixture(fixture_name)
    run_resp = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={
            "input": {
                "text": fix["input_text"],
                "extra": fix.get("extra", {}),
            },
            "include_trace": True,
        },
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]
    trace_resp = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace_resp.status_code == 200, (
        f"{agent_id}: RunTrace endpoint returned {trace_resp.status_code}"
    )
    trace_data = trace_resp.json()
    timeline = trace_data.get("timeline", trace_data.get("events", []))
    assert len(timeline) >= 1, (
        f"{agent_id}: RunTrace timeline empty for run_id={run_id}"
    )


# ── §7 #9: unknown non-medical-coding agent returns structured error ────


def test_f3_9_unknown_non_medical_coding_agent_returns_structured_error(
    client: TestClient,
) -> None:
    """§7 #9: unknown agent_id returns HTTP 200 with error=True.

    Mirrors F2 §8.1 #6 but for a non-medical-coding agent_id pattern,
    so the unified endpoint's _run_via_provider_registry path handles
    the unknown-agent case via _error_response(error_reason='unknown_agent').
    """
    resp = client.post(
        "/api/v1/agents/nonexistent-p0-agent-xyz/run",
        json={"input": {"text": "test input for unknown agent"}},
    )
    assert resp.status_code == 200, (
        f"Should be 200 with error=true, got {resp.status_code}"
    )
    data = resp.json()
    assert data["error"] is True, f"error should be True for unknown agent"
    assert data["error_reason"] == "unknown_agent", (
        f"error_reason should be 'unknown_agent', got: {data['error_reason']}"
    )
    assert "nonexistent-p0-agent-xyz" in data["summary"], (
        f"summary should mention the unknown agent_id"
    )
    assert data["agent_id"] == "nonexistent-p0-agent-xyz"
    assert data["run_id"].startswith("run-")
