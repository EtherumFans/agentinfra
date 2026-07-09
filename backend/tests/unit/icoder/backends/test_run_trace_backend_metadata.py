"""Tests for RunTrace backend provider metadata — Phase 4-A Task 8.

Verifies:
  - emit_backend_metadata_event writes a RunTrace event with all 8 backend fields.
  - All 8 keys are in _SAFE_KEYS so defensive redaction leaves them intact.
  - _redact_safe_metadata does NOT blank backend_provider / backend_type / etc.
  - Provider metadata is display-safe (no PHI / no token blobs).
  - Event carries duration_ms == provider_latency_ms.
"""
from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStep,
    RunTraceStore,
    _KNOWN_SECRET_KEYS,
    _SAFE_KEYS,
    _redact_safe_metadata,
    emit_backend_metadata_event,
    emit_trace_event,
)


# ── _SAFE_KEYS includes all 8 backend metadata keys ───────────────


@pytest.mark.parametrize("key", [
    "backend_provider", "backend_type", "provider_latency_ms",
    "provider_status", "provider_deterministic",
    "supports_tool_calling", "fallback_used", "output_contract",
    "tool_rounds",
])
def test_safe_keys_includes_backend_metadata(key):
    """All 8 backend metadata keys are in _SAFE_KEYS (Task 8 req #1, #2)."""
    assert key in _SAFE_KEYS


# ── _redact_safe_metadata doesn't blank backend fields ────────────


def test_redact_does_not_blank_backend_metadata():
    """Redaction scan leaves all 8 backend fields intact."""
    safe = {
        "backend_provider": "icoder.rule-engine.v1",
        "backend_type": "rule_engine",
        "provider_latency_ms": 42,
        "provider_status": "pass",
        "provider_deterministic": True,
        "supports_tool_calling": False,
        "fallback_used": False,
        "output_contract": "icoder/RuleEngineOutput/v1",
        "tool_rounds": 0,
    }
    scrubbed = _redact_safe_metadata(safe)
    assert scrubbed == safe  # No blanks


def test_redact_still_blanks_secret_keys():
    """Secret keys are still blanked — backend metadata change didn't break redaction."""
    safe = {
        "backend_provider": "icoder.rule-engine.v1",
        "token": "Bearer abc.def.ghi",  # should be blanked
        "api_key": "sk-1234567890",  # should be blanked
    }
    scrubbed = _redact_safe_metadata(safe)
    assert scrubbed["backend_provider"] == "icoder.rule-engine.v1"
    assert scrubbed["token"] == "[REDACTED]"
    assert scrubbed["api_key"] == "[REDACTED]"


# ── emit_backend_metadata_event ───────────────────────────────────


def test_emit_backend_metadata_event_writes_all_8_fields():
    """emit_backend_metadata_event writes a RunTrace event with all 8 fields."""
    store = RunTraceStore()
    run_id = "run-backend-1"
    event = emit_backend_metadata_event(
        run_id,
        backend_provider="icoder.rule-engine.v1",
        backend_type="rule_engine",
        provider_latency_ms=42,
        provider_status="pass",
        provider_deterministic=True,
        supports_tool_calling=False,
        fallback_used=False,
        output_contract="icoder/RuleEngineOutput/v1",
        tool_rounds=0,
        store=store,
    )
    assert event.step == RunTraceStep.OUTPUT_GENERATED
    assert event.duration_ms == 42.0  # provider_latency_ms mapped to duration_ms
    assert event.safe_metadata["backend_provider"] == "icoder.rule-engine.v1"
    assert event.safe_metadata["backend_type"] == "rule_engine"
    assert event.safe_metadata["provider_latency_ms"] == 42
    assert event.safe_metadata["provider_status"] == "pass"
    assert event.safe_metadata["provider_deterministic"] is True
    assert event.safe_metadata["supports_tool_calling"] is False
    assert event.safe_metadata["fallback_used"] is False
    assert event.safe_metadata["output_contract"] == "icoder/RuleEngineOutput/v1"
    assert event.safe_metadata["tool_rounds"] == 0


def test_emit_backend_metadata_event_persists_to_store():
    """Event is persisted to the store and retrievable via get_run()."""
    store = RunTraceStore()
    run_id = "run-persist-1"
    emit_backend_metadata_event(
        run_id,
        backend_provider="icoder.pure-llm.v1",
        backend_type="pure_llm",
        provider_latency_ms=5123,
        provider_status="complete",
        provider_deterministic=False,
        supports_tool_calling=False,
        fallback_used=True,
        output_contract="icoder/PureLLMOutput/v1",
        tool_rounds=0,
        store=store,
    )
    events = store.get_run(run_id)
    assert len(events) == 1
    assert events[0].safe_metadata["backend_provider"] == "icoder.pure-llm.v1"
    assert events[0].safe_metadata["fallback_used"] is True
    assert events[0].duration_ms == 5123.0


def test_emit_backend_metadata_event_defaults_step_to_output_generated():
    """Default step is OUTPUT_GENERATED (matches emit_trace_event convention)."""
    store = RunTraceStore()
    event = emit_backend_metadata_event(
        "run-default-step",
        backend_provider="x", backend_type="rule_engine",
        store=store,
    )
    assert event.step == RunTraceStep.OUTPUT_GENERATED


def test_emit_backend_metadata_event_can_use_custom_step():
    """Caller can override step (e.g. emit at EXPERT_RESPONSE for tool-calling providers)."""
    store = RunTraceStore()
    event = emit_backend_metadata_event(
        "run-custom-step",
        backend_provider="icoder.llm-with-tools.v1",
        backend_type="llm_with_tools",
        step=RunTraceStep.EXPERT_RESPONSE,
        store=store,
    )
    assert event.step == RunTraceStep.EXPERT_RESPONSE


def test_emit_backend_metadata_event_with_redaction_simulated():
    """Simulate the full write → redact → read cycle (DbRunTraceStore path)."""
    store = RunTraceStore()
    run_id = "run-redact-1"
    emit_backend_metadata_event(
        run_id,
        backend_provider="icoder.cascade.v1",
        backend_type="cascade",
        provider_latency_ms=999,
        provider_status="warning",
        provider_deterministic=False,
        supports_tool_calling=True,
        fallback_used=True,
        output_contract="icoder/OutputContract/v1",
        tool_rounds=3,
        store=store,
    )
    events = store.get_run(run_id)
    assert len(events) == 1
    # Simulate DB-layer redaction scan (would-be _redact_safe_metadata call).
    scrubbed = _redact_safe_metadata(events[0].safe_metadata)
    # All 8 backend fields survive the redaction scan.
    assert scrubbed["backend_provider"] == "icoder.cascade.v1"
    assert scrubbed["backend_type"] == "cascade"
    assert scrubbed["provider_latency_ms"] == 999
    assert scrubbed["provider_status"] == "warning"
    assert scrubbed["provider_deterministic"] is False
    assert scrubbed["supports_tool_calling"] is True
    assert scrubbed["fallback_used"] is True
    assert scrubbed["output_contract"] == "icoder/OutputContract/v1"
    assert scrubbed["tool_rounds"] == 3
