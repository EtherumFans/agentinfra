"""Tests for RunTrace backend provider metadata — Phase 4-A Task 8.

Verifies:
  - emit_backend_metadata_event writes provider and model-routing fields.
  - All keys are in _SAFE_KEYS so defensive redaction leaves them intact.
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
    "model_deployment_id", "model_routing_mode",
    "model_selection_version", "model_routing_decision",
    "model_provider", "model_system", "model_name", "input_tokens",
    "output_tokens", "total_tokens", "model_cost_usd", "finish_reason",
    "llm_call_count",
    "cost_amount", "cost_currency", "cost_source", "billing_authoritative",
    "clinical_asset_ids", "clinical_asset_versions",
    "clinical_asset_authority_statuses", "clinical_asset_license_statuses",
    "clinical_asset_integrity_verified", "semantic_enhancement_used",
    "candidate_codes_count", "query_terms_count", "rephrasing_attempted",
    "evidence_items_count", "valid_evidence_spans_count",
    "invalid_evidence_spans_count", "evidence_source_coverage_ratio",
    "evidence_input_codes_count", "evidence_located_mentions_count",
    "evidence_unmatched_codes_count",
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
        "model_deployment_id": "hospital-qwen-a",
        "model_routing_mode": "pinned",
        "model_selection_version": 7,
        "model_routing_decision": "tenant_pinned",
        "model_provider": "deepseek",
        "model_system": "deepseek",
        "model_name": "deepseek-chat",
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "model_cost_usd": 0.0001,
        "finish_reason": "stop",
        "llm_call_count": 1,
        "clinical_asset_ids": "cn.icd10cn.catalog",
        "clinical_asset_versions": "observed-local-2026-05-19",
        "clinical_asset_authority_statuses": "source_unverified",
        "clinical_asset_license_statuses": "external_review_required",
        "clinical_asset_integrity_verified": True,
        "semantic_enhancement_used": False,
        "candidate_codes_count": 3,
        "query_terms_count": 2,
        "rephrasing_attempted": True,
        "evidence_items_count": 3,
        "valid_evidence_spans_count": 1,
        "invalid_evidence_spans_count": 0,
        "evidence_source_coverage_ratio": 0.6667,
        "evidence_input_codes_count": 2,
        "evidence_located_mentions_count": 3,
        "evidence_unmatched_codes_count": 1,
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
        model_deployment_id="hospital-qwen-a",
        model_routing_mode="pinned",
        model_selection_version=7,
        model_routing_decision="tenant_pinned",
        model_provider="deepseek",
        model_system="deepseek",
        model_name="deepseek-chat",
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        model_cost_usd=0.0001,
        finish_reason="stop",
        llm_call_count=1,
        clinical_asset_ids="cn.icd10cn.catalog",
        clinical_asset_versions="observed-local-2026-05-19",
        clinical_asset_authority_statuses="source_unverified",
        clinical_asset_license_statuses="external_review_required",
        clinical_asset_integrity_verified=True,
        semantic_enhancement_used=False,
        candidate_codes_count=3,
        query_terms_count=2,
        rephrasing_attempted=True,
        evidence_items_count=3,
        valid_evidence_spans_count=1,
        invalid_evidence_spans_count=0,
        evidence_source_coverage_ratio=0.6667,
        evidence_input_codes_count=2,
        evidence_located_mentions_count=3,
        evidence_unmatched_codes_count=1,
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
    assert event.safe_metadata["model_deployment_id"] == "hospital-qwen-a"
    assert event.safe_metadata["model_routing_mode"] == "pinned"
    assert event.safe_metadata["model_selection_version"] == 7
    assert event.safe_metadata["model_routing_decision"] == "tenant_pinned"
    assert event.safe_metadata["model_provider"] == "deepseek"
    assert event.safe_metadata["model_system"] == "deepseek"
    assert event.safe_metadata["model_name"] == "deepseek-chat"
    assert event.safe_metadata["input_tokens"] == 11
    assert event.safe_metadata["output_tokens"] == 7
    assert event.safe_metadata["total_tokens"] == 18
    assert event.safe_metadata["model_cost_usd"] == 0.0001
    assert event.safe_metadata["finish_reason"] == "stop"
    assert event.safe_metadata["llm_call_count"] == 1
    assert event.safe_metadata["clinical_asset_ids"] == "cn.icd10cn.catalog"
    assert event.safe_metadata["clinical_asset_versions"] == "observed-local-2026-05-19"
    assert event.safe_metadata["clinical_asset_authority_statuses"] == "source_unverified"
    assert event.safe_metadata["clinical_asset_license_statuses"] == "external_review_required"
    assert event.safe_metadata["clinical_asset_integrity_verified"] is True
    assert event.safe_metadata["semantic_enhancement_used"] is False
    assert event.safe_metadata["candidate_codes_count"] == 3
    assert event.safe_metadata["query_terms_count"] == 2
    assert event.safe_metadata["rephrasing_attempted"] is True
    assert event.safe_metadata["evidence_items_count"] == 3
    assert event.safe_metadata["valid_evidence_spans_count"] == 1
    assert event.safe_metadata["invalid_evidence_spans_count"] == 0
    assert event.safe_metadata["evidence_source_coverage_ratio"] == 0.6667
    assert event.safe_metadata["evidence_input_codes_count"] == 2
    assert event.safe_metadata["evidence_located_mentions_count"] == 3
    assert event.safe_metadata["evidence_unmatched_codes_count"] == 1


def test_emit_backend_metadata_rejects_unbounded_or_free_form_model_telemetry():
    event = emit_backend_metadata_event(
        "run-bounded-telemetry",
        backend_provider="icoder.pure-llm.v1",
        backend_type="pure_llm",
        model_provider="deepseek\nAuthorization: Bearer secret",
        model_name="患者张三的模型",
        input_tokens=-1,
        output_tokens=100_000_001,
        model_cost_usd=float("inf"),
        finish_reason="stop because patient text followed",
        evidence_items_count=-1,
        valid_evidence_spans_count=100_000_001,
        invalid_evidence_spans_count="not-a-count",
        evidence_source_coverage_ratio=1.5,
        evidence_input_codes_count=-1,
        evidence_located_mentions_count=100_000_001,
        evidence_unmatched_codes_count="not-a-count",
        store=RunTraceStore(),
    )
    assert "model_provider" not in event.safe_metadata
    assert "model_name" not in event.safe_metadata
    assert "input_tokens" not in event.safe_metadata
    assert "output_tokens" not in event.safe_metadata
    assert "model_cost_usd" not in event.safe_metadata
    assert "finish_reason" not in event.safe_metadata
    assert "evidence_items_count" not in event.safe_metadata
    assert "valid_evidence_spans_count" not in event.safe_metadata
    assert "invalid_evidence_spans_count" not in event.safe_metadata
    assert "evidence_source_coverage_ratio" not in event.safe_metadata
    assert "evidence_input_codes_count" not in event.safe_metadata
    assert "evidence_located_mentions_count" not in event.safe_metadata
    assert "evidence_unmatched_codes_count" not in event.safe_metadata


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


def test_cdi_latency_attribution_fields_survive_strict_allowlist():
    scrubbed = _redact_safe_metadata({
        "orchestration_latency_ms": 120,
        "instrumented_stage_latency_ms": 105,
        "model_call_latency_sum_ms": 150,
        "non_provider_wall_latency_ms": 30,
        "non_provider_wall_latency_known": False,
        "parallel_model_calls_observed": True,
        "provider_latency_exceeds_wall_time": True,
        "slowest_stage": "semantic_necessity_gate",
        "slowest_stage_latency_ms": 45,
        "latency_budget_ms": 100,
        "latency_budget_exceeded": True,
        "clinical_text": "must be removed",
    })

    assert scrubbed == {
        "orchestration_latency_ms": 120,
        "instrumented_stage_latency_ms": 105,
        "model_call_latency_sum_ms": 150,
        "non_provider_wall_latency_ms": 30,
        "non_provider_wall_latency_known": False,
        "parallel_model_calls_observed": True,
        "provider_latency_exceeds_wall_time": True,
        "slowest_stage": "semantic_necessity_gate",
        "slowest_stage_latency_ms": 45,
        "latency_budget_ms": 100,
        "latency_budget_exceeded": True,
        "clinical_text": "[REDACTED]",
    }
