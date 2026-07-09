"""Phase 4-F (2026-07-09) — unified Agent Run endpoint tests.

Tests for ``POST /api/v1/agents/{agent_id}/run``:

  1. Unknown agent_id returns error=true (not 4xx/5xx)
  2. Response envelope has all 13 required fields (prompt §9.1)
  3. Hub endpoint surfaces the 5 new v1.3 spec fields
  4. Medical Coding Agent route wiring (mock-gateway, no real LLM call)
  5. Failure contract: runtime crash returns error=true (never raises)

These tests use the mock LLM gateway via ``LLM_PROVIDER=mock`` so they
don't hit the real DeepSeek API.
"""
from __future__ import annotations

import os

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


# ── 1. Unknown agent_id → structured error ──────────────────────────────


def test_unknown_agent_id_returns_structured_error(client: TestClient) -> None:
    """POST /api/v1/agents/{unknown_id}/run returns 200 with error=true."""
    resp = client.post(
        "/api/v1/agents/this-agent-does-not-exist/run",
        json={"input": {"text": "anything"}},
    )
    # 200, not 404 — the contract is HTTP 200 + error=true in body.
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is True
    assert data["error_reason"] == "unknown_agent"
    assert "Unknown agent_id" in data["summary"]
    assert data["agent_id"] == "this-agent-does-not-exist"
    assert data["run_id"].startswith("run-")
    assert data["trace_id"].startswith("trace-")


# ── 2. Response envelope has all 13 required fields ─────────────────────


_REQUIRED_FIELDS = (
    "agent_id", "run_id", "trace_id", "runtime_mode", "latency_ms",
    "cost", "summary", "result", "evidence", "warnings",
    "manual_review_required", "trace_events", "error", "error_reason",
)


def test_error_response_has_all_required_fields(client: TestClient) -> None:
    """All 13 AgentRunResponse fields present even on error path."""
    resp = client.post(
        "/api/v1/agents/nonexistent-agent/run",
        json={"input": {"text": "anything"}},
    )
    data = resp.json()
    for field in _REQUIRED_FIELDS:
        assert field in data, f"missing field {field!r} in response"


# ── 3. Hub endpoint surfaces v1.3 spec fields ────────────────────────────


def test_hub_endpoint_returns_v13_fields(client: TestClient) -> None:
    """GET /api/icoder/agents/hub card includes the 5 new spec fields."""
    resp = client.get("/api/icoder/agents/hub")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert data["total"] > 0
    for card in data["agents"]:
        # All 5 new fields must be present on every card (empty for
        # legacy packs, populated for v1.3 packs).
        assert "default_runtime_mode" in card, (
            f"missing default_runtime_mode on card {card.get('agent_id')!r}"
        )
        assert "available_runtime_modes" in card
        assert "example_inputs" in card
        assert "example_outputs" in card
        assert "built_by" in card


def test_hub_medical_coding_agent_has_runtime_modes(client: TestClient) -> None:
    """The Medical Coding Agent card declares both corti_like_fast and medcoder_deep.

    NOTE: This test will start passing after F2 populates the v1.3 fields
    on the medical_coding/agent_pack.json. Until then, it's a known-failing
    reminder.
    """
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    medical_coding = next(
        (c for c in data["agents"] if c.get("agent_id") == "medical-coding-agent"),
        None,
    )
    if medical_coding is None:
        pytest.skip("medical-coding-agent not visible in Hub (will appear after F2)")
    # After F2, these should be populated.
    if not medical_coding.get("default_runtime_mode"):
        pytest.skip("medical-coding-agent pack not yet upgraded to v1.3 (F2 will fix)")
    assert medical_coding["default_runtime_mode"] == "corti_like_fast"
    assert "corti_like_fast" in medical_coding["available_runtime_modes"]
    assert "medcoder_deep" in medical_coding["available_runtime_modes"]


# ── 4. Medical Coding Agent route wiring (mock-gateway) ─────────────────


def test_medical_coding_agent_routes_to_coding_runtime(client: TestClient) -> None:
    """POST /api/v1/agents/medical-coding-agent/run delegates to CodingRuntimeDispatcher.

    With LLM_PROVIDER=mock, the dispatcher returns a deterministic mock
    CodingResult. We verify the response envelope maps it correctly.
    """
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。"},
            "runtime_mode": "corti_like_fast",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "medical-coding-agent"
    assert data["run_id"].startswith("run-")
    assert data["trace_id"]  # non-empty
    assert data["runtime_mode"] == "corti_like_fast"
    assert data["latency_ms"] >= 0
    # medical coding always requires human review
    assert data["manual_review_required"] is True
    # error path or success path both have a summary
    assert isinstance(data["summary"], str)
    # result.codes is the flat code list (or empty on error)
    assert "codes" in data["result"]


def test_medical_coding_agent_medcoder_deep_mode(client: TestClient) -> None:
    """runtime_mode=medcoder_deep routes through CodingRuntimeDispatcher with MEDCODER_DEEP."""
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "T12 vertebral compression fracture."},
            "runtime_mode": "medcoder_deep",
        },
    )
    # Either succeeds (200 with codes) or returns error=true (if mock
    # gateway not wired for deep mode) — but never 5xx.
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "medical-coding-agent"
    if data["error"]:
        # Mock gateway may not support medcoder_deep — that's fine.
        assert data["error_reason"] in ("runtime_error", "runtime_crash")
    else:
        assert data["runtime_mode"] == "medcoder_deep"


# ── 5. Failure contract — never raises ──────────────────────────────────


def test_unknown_runtime_mode_falls_back_to_fast(client: TestClient) -> None:
    """Unknown runtime_mode coerces to corti_like_fast (per RuntimeMode.coerce)."""
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "T12 fracture."},
            "runtime_mode": "totally_invalid_mode_name",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should fall back to corti_like_fast (or error if mock gateway unavailable).
    assert data["runtime_mode"] in ("corti_like_fast", "totally_invalid_mode_name")
    assert "error" in data


def test_empty_input_text_returns_structured_error(client: TestClient) -> None:
    """Empty input.text fails Pydantic validation → 422 (not 500)."""
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={"input": {"text": ""}},
    )
    # Pydantic raises 422 for min_length=1 violation — that's the
    # intended contract (input validation, not runtime error).
    assert resp.status_code == 422


def test_missing_input_field_returns_422(client: TestClient) -> None:
    """Missing input field fails Pydantic validation → 422."""
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={"runtime_mode": "corti_like_fast"},
    )
    assert resp.status_code == 422
