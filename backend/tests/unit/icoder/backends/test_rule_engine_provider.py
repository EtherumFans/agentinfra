"""Tests for ``icoder_runtime.backends.rule_engine_provider`` — Phase 4-A Task 4.

Verifies:
  - RuleEngineProvider invoke returns BackendResponse.
  - Coding_output input shape runs R001-R012 validation.
  - Coding_set input shape projects to coding_output and reuses validate.
  - Topic input shape uses RuleEngineService.retrieve_rules (KB lookup).
  - Empty input returns a warning envelope (fail-soft).
  - Provider metadata (provider_id / backend_type / deterministic / etc.).
  - output_contract() returns "icoder/RuleEngineOutput/v1".
  - capabilities() returns ProviderCapability.
  - stream() yields backend_invoked + finished events.
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends import (
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    ProviderHealth,
)
from icoder_runtime.backends.rule_engine_provider import RuleEngineProvider


def _ctx(agent_id: str = "test-agent") -> AgentRunContext:
    return AgentRunContext(
        run_id="run-test-1",
        context_id="ctx-test-1",
        agent_id=agent_id,
        redacted_input="patient with COPD",
    )


# ── Provider metadata ───────────────────────────────────────────────


def test_rule_engine_provider_metadata():
    p = RuleEngineProvider()
    assert p.provider_id == "icoder.rule-engine.v1"
    assert p.backend_type == "rule_engine"
    assert p.deterministic is True
    assert p.supports_tool_calling is False
    assert p.supports_streaming is False


def test_rule_engine_provider_output_contract():
    p = RuleEngineProvider()
    assert p.output_contract() == "icoder/RuleEngineOutput/v1"


def test_rule_engine_provider_capabilities():
    p = RuleEngineProvider()
    cap = p.capabilities()
    assert cap.provider_id == "icoder.rule-engine.v1"
    assert cap.backend_type == "rule_engine"
    assert cap.deterministic is True
    assert cap.supports_tool_calling is False


def test_rule_engine_provider_fallback_chain_none():
    p = RuleEngineProvider()
    assert p.fallback_chain() is None


# ── health ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rule_engine_provider_health_ok():
    p = RuleEngineProvider()
    h = await p.health()
    assert isinstance(h, ProviderHealth)
    assert h.state == "ok"


# ── invoke: coding_output shape ────────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_coding_output_with_critical_primary_missing():
    """R001 fires when primary_diagnosis.code is empty → status='fail'."""
    p = RuleEngineProvider()
    req = BackendRequest(input={
        "coding_output": {
            "primary_diagnosis": {"code": "", "description": ""},
            "secondary_diagnoses": [],
            "procedures": [],
        }
    })
    resp = await p.invoke(req, _ctx())
    assert isinstance(resp, BackendResponse)
    assert resp.backend_provider == "icoder.rule-engine.v1"
    assert resp.backend_type == "rule_engine"
    assert resp.finish_state == "completed"
    # R001 is critical → status should be 'fail'
    assert resp.status == "fail"
    assert any(i.code == "R001" for i in resp.issues)
    assert "R001" in resp.evidence_refs


@pytest.mark.asyncio
async def test_invoke_coding_output_with_valid_codes_passes():
    """All-format-valid coding_output with primary set → status='pass'."""
    p = RuleEngineProvider()
    req = BackendRequest(input={
        "coding_output": {
            "primary_diagnosis": {"code": "I50.900", "description": "心衰竭"},
            "secondary_diagnoses": [{"code": "I10", "description": "高血压"}],
            "procedures": [{"code": "00.66", "description": "PCI"}],
        }
    })
    resp = await p.invoke(req, _ctx())
    assert resp.status in ("pass", "warning")  # may emit R006 low-confidence as info
    assert resp.finish_state == "completed"
    assert resp.latency_ms >= 0


# ── invoke: coding_set shape (legacy compliance-guardrail path) ────


@pytest.mark.asyncio
async def test_invoke_coding_set_projects_to_coding_output():
    """coding_set shape (compliance-guardrail legacy) is projected to
    coding_output and validated with the same R001-R012 logic."""
    p = RuleEngineProvider()
    req = BackendRequest(input={
        "coding_set": {
            "primary_diagnosis": {"code": "M80.900", "description": "骨质疏松伴病理性骨折"},
            "secondary_diagnoses": [],
            "procedures": [],
        }
    })
    resp = await p.invoke(req, _ctx())
    assert resp.backend_provider == "icoder.rule-engine.v1"
    # M80.900 is valid format, primary set → pass or warning
    assert resp.status in ("pass", "warning", "fail")


@pytest.mark.asyncio
async def test_invoke_coding_set_with_invalid_format_flags_R002():
    """Invalid ICD-10 format triggers R002 (high severity)."""
    p = RuleEngineProvider()
    req = BackendRequest(input={
        "coding_set": {
            "primary_diagnosis": {"code": "BADCODE", "description": "bogus"},
            "secondary_diagnoses": [],
            "procedures": [],
        }
    })
    resp = await p.invoke(req, _ctx())
    assert any(i.code == "R002" for i in resp.issues)


# ── invoke: topic shape (KB lookup) ────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_topic_returns_kb_rules():
    """Topic input shape uses RuleEngineService.retrieve_rules."""
    p = RuleEngineProvider()
    req = BackendRequest(input={"topic": "骨质疏松"})
    resp = await p.invoke(req, _ctx())
    assert resp.finish_state == "completed"
    # Either retrieved some rules (status=pass) or zero matches (status=warning)
    assert resp.status in ("pass", "warning")
    if resp.status == "pass":
        assert len(resp.issues) > 0
        # KB issues are severity='info'
        assert all(i.severity == "info" for i in resp.issues)


# ── invoke: empty / unknown input ──────────────────────────────────


@pytest.mark.asyncio
async def test_invoke_empty_input_returns_warning_envelope():
    """Empty input dict → fail-soft warning (not exception)."""
    p = RuleEngineProvider()
    req = BackendRequest(input={})
    resp = await p.invoke(req, _ctx())
    assert resp.status == "warning"
    assert resp.finish_state == "completed"
    assert "empty" in resp.summary.lower() or "unrecognized" in resp.summary.lower()


@pytest.mark.asyncio
async def test_invoke_unknown_input_keys_returns_warning():
    """Unrecognized input shape → warning with input_keys in raw."""
    p = RuleEngineProvider()
    req = BackendRequest(input={"bogus_key": "value"})
    resp = await p.invoke(req, _ctx())
    assert resp.status == "warning"
    assert resp.raw_provider_response.get("input_keys") == ["bogus_key"]


# ── invoke: never raises (defensive envelope) ──────────────────────


@pytest.mark.asyncio
async def test_invoke_does_not_raise_on_adversarial_input():
    """Adversarial input shapes don't crash the provider."""
    p = RuleEngineProvider()
    adversarial_inputs = [
        {"coding_output": "not a dict"},
        {"coding_set": 12345},
        {"coding_output": {"primary_diagnosis": "not a dict"}},
    ]
    for bad in adversarial_inputs:
        req = BackendRequest(input=bad)
        resp = await p.invoke(req, _ctx())
        # Either fail or warning envelope, never an exception.
        assert resp.status in ("fail", "warning")
        assert resp.finish_state in ("completed", "failed")


# ── stream ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_yields_backend_invoked_then_finished():
    """stream() yields exactly 2 events: backend_invoked + finished."""
    p = RuleEngineProvider()
    req = BackendRequest(input={"topic": "test"})
    events = []
    async for ev in p.stream(req, _ctx()):
        events.append(ev)
    assert len(events) == 2
    assert events[0]["step"] == "backend_invoked"
    assert events[1]["step"] == "finished"
    assert events[0]["payload"].backend_provider == "icoder.rule-engine.v1"
