"""Phase 4-F3 (2026-07-10) — Core Agent Smoke Runs (non-Medical-Coding).

Tests the 9 requirements per prompt §7 — 4 P0 non-Medical-Coding agents
(evidence-extractor, principal-diagnosis-review, drg-analyzer,
discharge-summary-structuring) run stably via the A2A-compatible
unified Agent Run endpoint and produce structured envelopes.

Current architecture:
  - All four agents use governed deterministic local providers and publish
    their full contracts offline.
  - Legacy free-text fixtures must fail safe with INPUT_REQUIRED where the
    current contract requires explicit, evidence-bound structured inputs.
  - Tests assert both the common envelope and the safety boundary appropriate
    to each execution path; no real model or browser session is required.
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
    if agent_id == "evidence-extractor":
        assert data["error"] is False
        assert data["result"]["extraction_status"] == "COMPLETED"
        assert data["result"]["match_basis"] == (
            "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"
        )
        assert data["result"]["uncoded_findings"] == []
    elif agent_id == "principal-diagnosis-review":
        result = data["result"]
        assert data["error"] is False
        assert result["backend_provider"] == (
            "icoder.governed-principal-diagnosis-review.v1"
        )
        assert result["backend_type"] == "rule_engine"
        assert result["review_status"] == "INPUT_REQUIRED"
        assert result["review_method"] == (
            "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"
        )
        assert result["diagnosis_extraction_performed"] is False
        assert result["code_assignment_performed"] is False
        assert result["principal_diagnosis_selection_performed"] is False
        assert result["clinical_inference_performed"] is False
        assert result["production_writeback_blocked"] is True
        assert result["manual_review_required"] is True
    elif agent_id == "drg-analyzer":
        result = data["result"]
        assert data["error"] is False
        assert result["backend_provider"] == (
            "icoder.governed-drg-dip-risk-review.v1"
        )
        assert result["backend_type"] == "rule_engine"
        assert result["review_status"] == "INPUT_REQUIRED"
        assert result["review_method"] == (
            "EXPLICIT_CODED_CASE_DETERMINISTIC_UNVERIFIED_RISK_REVIEW"
        )
        assert result["local_development_rules_used"] is False
        assert result["official_grouping_performed"] is False
        assert result["official_dip_scoring_performed"] is False
        assert result["payment_calculation_performed"] is False
        assert result["billing_authoritative"] is False
        assert result["production_writeback_blocked"] is True
        assert result["manual_review_required"] is True
    elif agent_id == "discharge-summary-structuring":
        # The legacy single-paragraph fixture has no supported line-level
        # headings. The governed local parser must not summarize it anyway.
        result = data["result"]
        assert data["error"] is False
        assert result["backend_provider"] == (
            "icoder.governed-discharge-summary.v1"
        )
        assert result["backend_type"] == "rule_engine"
        assert result["structuring_status"] == "INPUT_REQUIRED"
        assert result["diagnoses"] == []
        assert result["procedures"] == []
        assert result["discharge_orders"] == []
        assert result["follow_up_recommendations"] == []
        assert result["evidence_items"] == []
        assert result["summary_generation_status"] == (
            "VERBATIM_SECTION_REORGANIZATION_ONLY"
        )
        assert result["icd_codes_assigned"] is False
        assert result["medication_reconciliation_performed"] is False
        assert result["clinical_inference_performed"] is False
        assert result["production_writeback_blocked"] is True
        assert result["manual_review_required"] is True


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


# ── §7 #5: runtime_mode matches the authoritative execution path ────────


@pytest.mark.parametrize("agent_id,fixture_name", P0_AGENTS)
def test_f3_5_runtime_mode_matches_authoritative_execution_path(
    client: TestClient, agent_id: str, fixture_name: str,
) -> None:
    """§7 #5: runtime_mode reflects each agent's default_runtime_mode.

    The response runtime_mode must match the pack's authoritative local or
    external execution mode.
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
    expected = {
        "evidence-extractor": "governed_local_exact_mention_extraction",
        "principal-diagnosis-review": "rule_engine",
        "drg-analyzer": "governed_local_explicit_coded_case_risk_review",
        "discharge-summary-structuring": "rule_engine",
    }[agent_id]
    assert data["runtime_mode"] == expected, (
        f"{agent_id}: runtime_mode should be {expected!r}, "
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
    assert data["manual_review_required"] is True
    assert data["result"] == {"contract_output_suppressed": True}
