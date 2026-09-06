"""Public Agent Run projection must not expose opaque provider payloads."""

import json
import pytest
import time
from pathlib import Path
from types import SimpleNamespace

from app.api.agent_run import (
    _derive_contract,
    _map_backend_response,
    _map_coding_result,
    _run_cdi_agent,
)
from app.coding_runtime.base import CodingResult, CodingResultCode
from icoder_runtime.backends.contracts import BackendResponse


def test_cdi_runtime_cost_estimate_reaches_public_run_without_becoming_invoice(
    monkeypatch,
) -> None:
    from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler

    monkeypatch.setattr(
        CDIA2AHandler,
        "handle",
        lambda self, agent_id, envelope: SimpleNamespace(
            kind="message",
            error=None,
            metadata={
                "runtime_mode": "cdi_real_orchestrator",
                "cost": {
                    "amount": 0.00050321,
                    "currency": "CNY",
                    "source": "configured_usage_pricing_estimate",
                    "billing_authoritative": False,
                },
            },
            parts=[{"kind": "data", "data": {"trace_refs": {}}}],
        ),
    )

    response = _run_cdi_agent(
        agent_id="clinical-documentation-improvement-agent",
        envelope=SimpleNamespace(metadata={}),
        run_id="run-cdi-cost",
        trace_id="trace-cdi-cost",
        t0=time.perf_counter(),
    )

    assert response.cost == {
        "amount": 0.00050321,
        "currency": "CNY",
        "source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }


def test_cdi_runtime_rejects_invoice_like_or_malformed_cost(monkeypatch) -> None:
    from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler

    monkeypatch.setattr(
        CDIA2AHandler,
        "handle",
        lambda self, agent_id, envelope: SimpleNamespace(
            kind="message",
            error=None,
            metadata={
                "runtime_mode": "cdi_real_orchestrator",
                "cost": {
                    "amount": 9.0,
                    "currency": "USD",
                    "source": "provider_invoice",
                    "billing_authoritative": True,
                },
            },
            parts=[{"kind": "data", "data": {"trace_refs": {}}}],
        ),
    )

    response = _run_cdi_agent(
        agent_id="clinical-documentation-improvement-agent",
        envelope=SimpleNamespace(metadata={}),
        run_id="run-cdi-bad-cost",
        trace_id="trace-cdi-bad-cost",
        t0=time.perf_counter(),
    )

    assert response.cost == {}


def test_public_projection_omits_raw_provider_response() -> None:
    secret_marker = "provider-secret-debug-marker"
    response = BackendResponse(
        status="requires_review",
        summary="Safe summary",
        markdown="Safe markdown",
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
        raw_provider_response={"internal": secret_marker},
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-1",
        trace_id="trace-1",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        t0=time.perf_counter(),
    )

    assert "raw_provider_response" not in public.result
    assert secret_marker not in repr(public.model_dump())


def test_visible_agent_contracts_are_read_from_their_pack() -> None:
    official_agents = Path(__file__).resolve().parents[4] / "official_agents"
    checked = 0
    for pack_path in official_agents.glob("*/agent_pack.json"):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        checked += 1
        assert _derive_contract(pack) == pack["output_contract"]["schema_ref"]
    assert checked == 26


def test_pack_contract_is_projected_and_validated() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision", "manual_review_required"],
            "field_types": {
                "decision": "string",
                "manual_review_required": "boolean",
            },
        }
    }
    response = BackendResponse(
        status="requires_review",
        summary="Safe summary",
        markdown=(
            "```json\n"
            '{"decision":"review","manual_review_required":true}'
            "\n```"
        ),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-valid",
        trace_id="trace-contract-valid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["contract"] == "icoder/TestAgentOutput/v1"
    assert extraction["missing_required_fields"] == []
    assert extraction["invalid_field_types"] == []
    assert extraction["valid"] is True
    assert public.error is False


def test_wrong_pack_contract_field_type_fails_closed_without_value_leak() -> None:
    secret_chart_value = "patient-secret-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision", "manual_review_required"],
            "field_types": {
                "decision": "string",
                "manual_review_required": "boolean",
            },
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Malformed structured output",
        markdown=json.dumps({
            "decision": [secret_chart_value],
            "manual_review_required": True,
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-wrong-type",
        trace_id="trace-contract-wrong-type",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["missing_required_fields"] == []
    assert extraction["invalid_field_types"] == [
        {"field": "decision", "expected": "string", "actual": "array"}
    ]
    assert secret_chart_value not in repr(extraction)
    assert extraction["valid"] is False
    assert public.error is True
    assert public.error_reason == "output_contract_violation"
    assert public.manual_review_required is True
    assert public.result["contract_output_suppressed"] is True
    assert public.result["markdown"] == ""
    assert secret_chart_value not in repr(public.model_dump())


def test_nested_contract_violation_fails_closed_without_key_or_value_leak() -> None:
    secret = "patient-secret-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v2",
            "required_fields": ["evidence"],
            "field_types": {"evidence": "array"},
            "field_schemas": {
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["text", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Malformed nested output",
        markdown=json.dumps({
            "evidence": [{
                "text": secret,
                "confidence": "high",
                secret: secret,
            }]
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-nested-invalid",
        trace_id="trace-nested-invalid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["invalid_field_types"] == []
    assert extraction["invalid_field_schemas"] == [
        {
            "path": "evidence[]",
            "keyword": "additionalProperties",
            "expected": "none",
            "actual": "undeclared_property",
        },
        {
            "path": "evidence[].confidence",
            "keyword": "type",
            "expected": "number",
            "actual": "string",
        },
    ]
    assert extraction["valid"] is False
    assert public.error_reason == "output_contract_violation"
    assert public.result["contract_output_suppressed"] is True
    assert secret not in repr(public.model_dump())


def test_evidence_binding_violation_suppresses_provider_output_phi_safely() -> None:
    secret = "patient-secret-binding-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestEvidenceOutput/v1",
            "required_fields": ["findings"],
            "field_types": {"findings": "array"},
            "field_schemas": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_text": {"type": "string"},
                            "char_span": {
                                "type": "array",
                                "items": {"type": "integer", "minimum": 0},
                                "minItems": 2,
                                "maxItems": 2,
                                "x-order": "nondecreasing",
                            },
                        },
                        "required": ["evidence_text", "char_span"],
                        "additionalProperties": False,
                    },
                }
            },
            "evidence_bindings": [{
                "id": "finding_evidence_matches_input",
                "for_each": "findings",
                "text_path": "evidence_text",
                "span_path": "char_span",
            }],
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Malformed bound evidence",
        markdown=json.dumps({
            "findings": [{"evidence_text": secret, "char_span": [3, 5]}]
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-binding-invalid",
        trace_id="trace-binding-invalid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        source_text="诊断：肺炎。",
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["invalid_field_schemas"] == [{
        "path": "findings[].evidence_text",
        "keyword": "evidenceBinding",
        "expected": "finding_evidence_matches_input",
        "actual": "source_text_mismatch",
    }]
    assert extraction["valid"] is False
    assert public.result["contract_output_suppressed"] is True
    assert secret not in repr(public.model_dump())


def test_multidocument_binding_is_enforced_at_public_projection_boundary() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestDocumentEvidenceOutput/v1",
            "required_fields": ["findings"],
            "field_types": {"findings": "array"},
            "field_schemas": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quote": {"type": "string"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                            "document_id": {"type": "string"},
                        },
                        "required": ["quote", "start", "end", "document_id"],
                        "additionalProperties": False,
                    },
                }
            },
            "evidence_bindings": [{
                "id": "finding_matches_document",
                "for_each": "findings",
                "text_path": "quote",
                "start_path": "start",
                "end_path": "end",
                "document_id_path": "document_id",
            }],
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Bound evidence",
        markdown=json.dumps({
            "findings": [{
                "quote": "AB", "start": 0, "end": 2, "document_id": "doc-1",
            }]
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-document-binding",
        trace_id="trace-document-binding",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        source_text="primary",
        source_documents=[{
            "document_id": "doc-1", "text": "ＡＢ finding", "normalization": "NFKC",
        }],
        t0=time.perf_counter(),
    )

    assert public.error is False
    assert public.result["structured_extraction"]["valid"] is True


def test_cross_agent_conflict_suppresses_provider_output_phi_safely() -> None:
    secret = "patient-secret-cross-agent-code"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestCrossAgentOutput/v1",
            "required_fields": ["recommended"],
            "field_types": {"recommended": "object"},
            "field_schemas": {
                "recommended": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                    "additionalProperties": False,
                }
            },
            "cross_agent_relations": [{
                "id": "recommended_matches_diagnosis",
                "local_path": "recommended.code",
                "upstream_agent_id": "diagnosis-extractor",
                "upstream_path": "diagnoses",
                "upstream_item_path": "code",
                "operator": "scalar_in_upstream_items",
                "required": True,
            }],
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Conflicting code",
        markdown=json.dumps({"recommended": {"code": secret}}),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-cross-agent",
        trace_id="trace-cross-agent",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        source_text="primary",
        upstream_results=[{
            "agent_id": "diagnosis-extractor",
            "result": {"diagnoses": [{"code": "I21.0"}]},
        }],
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["invalid_cross_agent_relations"][0]["actual"] == (
        "scalar_in_upstream_items_violated"
    )
    assert public.error_reason == "output_contract_violation"
    assert public.result["contract_output_suppressed"] is True
    assert secret not in repr(public.model_dump())


def test_semantic_contract_violation_fails_closed_without_value_leak() -> None:
    secret = "patient-secret-semantic-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v3",
            "required_fields": ["status", "evidence", "manual_review_required"],
            "field_types": {
                "status": "string",
                "evidence": "array",
                "manual_review_required": "boolean",
            },
            "field_schemas": {
                "status": {"type": "string", "enum": ["PASS"]},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "char_span": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 2,
                                "x-order": "nondecreasing",
                                "items": {"type": "integer", "minimum": 0},
                            },
                        },
                        "required": ["text", "confidence", "char_span"],
                        "additionalProperties": False,
                    },
                },
                "manual_review_required": {"type": "boolean", "const": True},
            },
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Malformed semantic output",
        markdown=json.dumps({
            "status": secret,
            "evidence": [{"text": secret, "confidence": 1.1, "char_span": [9, 2]}],
            "manual_review_required": False,
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-semantic-invalid",
        trace_id="trace-semantic-invalid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert {item["keyword"] for item in extraction["invalid_field_schemas"]} == {
        "enum", "maximum", "x-order",
    }
    # Runtime-owned constants are projected authoritatively before semantic
    # validation; the model cannot switch mandatory review off.
    assert not any(
        item["keyword"] == "const"
        for item in extraction["invalid_field_schemas"]
    )
    assert extraction["valid"] is False
    assert public.error_reason == "output_contract_violation"
    assert public.result["contract_output_suppressed"] is True
    assert secret not in repr(public.model_dump())


def test_cross_field_relation_violation_fails_closed_without_value_leak() -> None:
    secret = "patient-secret-cross-field-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v4",
            "required_fields": ["items", "total_count"],
            "field_types": {"items": "array", "total_count": "integer"},
            "field_schemas": {
                "items": {"type": "array", "items": {"type": "string"}},
                "total_count": {"type": "integer"},
            },
            "field_relations": [{
                "id": "item_count_matches",
                "when": [{"path": "items", "operator": "present"}],
                "must": [{
                    "path": "items",
                    "operator": "length_equals",
                    "other_path": "total_count",
                }],
            }],
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Malformed cross-field output",
        markdown=json.dumps({"items": [secret], "total_count": 2}),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-cross-field-invalid",
        trace_id="trace-cross-field-invalid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["invalid_field_schemas"] == [{
        "path": "items",
        "keyword": "fieldRelation",
        "expected": "item_count_matches",
        "actual": "length_equals_violated",
    }]
    assert extraction["valid"] is False
    assert public.error_reason == "output_contract_violation"
    assert public.result["contract_output_suppressed"] is True
    assert secret not in repr(public.model_dump())


def test_undeclared_provider_field_fails_closed_without_value_leak() -> None:
    secret_chart_value = "undeclared-patient-secret-marker"
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision"],
            "field_types": {"decision": "string"},
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Provider output",
        markdown=json.dumps({
            "decision": "review",
            "debug_payload": secret_chart_value,
        }),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-extra",
        trace_id="trace-contract-extra",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["missing_required_fields"] == []
    assert extraction["invalid_field_types"] == []
    assert extraction["undeclared_output_fields"] == ["<redacted>"]
    assert extraction["undeclared_output_field_count"] == 1
    assert extraction["valid"] is False
    assert public.error_reason == "output_contract_violation"
    assert secret_chart_value not in repr(public.model_dump())


def test_transport_defaults_cannot_satisfy_domain_contract_fields() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["status", "markdown", "corrected_draft"],
            "field_types": {
                "status": "string",
                "markdown": "string",
                "corrected_draft": "string",
            },
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Transport values are not domain output",
        markdown="{}",
        corrected_draft="transport draft",
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-transport-mask",
        trace_id="trace-contract-transport-mask",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    assert public.result["structured_extraction"]["missing_required_fields"] == [
        "status", "markdown", "corrected_draft"
    ]
    assert public.error_reason == "output_contract_violation"


def test_declared_optional_field_is_allowed_and_type_checked() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision"],
            "optional_fields": ["details"],
            "field_types": {"decision": "string", "details": "array"},
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Valid optional field",
        markdown='{"decision":"review","details":[]}',
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-optional",
        trace_id="trace-contract-optional",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["optional_fields"] == ["details"]
    assert extraction["undeclared_output_fields"] == []
    assert extraction["invalid_field_types"] == []
    assert extraction["valid"] is True
    assert public.result["details"] == []


def test_missing_pack_contract_fields_fail_closed() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision", "evidence"],
        }
    }
    response = BackendResponse(
        status="pass",
        summary="Incomplete structured output",
        markdown='```json\n{"decision":"pass"}\n```',
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-contract-invalid",
        trace_id="trace-contract-invalid",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=False,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["missing_required_fields"] == ["evidence"]
    assert extraction["valid"] is False
    assert public.error is True
    assert public.error_reason == "output_contract_violation"
    assert public.manual_review_required is True


def test_empty_provider_output_cannot_bypass_pack_contract() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision"],
        }
    }
    response = BackendResponse(
        status="pass", summary="Provider claimed success", markdown="",
        backend_provider="test.provider.v1", backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent", run_id="run-empty", trace_id="trace-empty",
        runtime_mode="pure_llm", resp=response, include_trace=False,
        include_evidence=False, agent_pack=pack, t0=time.perf_counter(),
    )

    extraction = public.result["structured_extraction"]
    assert extraction["method"] == "none"
    assert extraction["missing_required_fields"] == ["decision"]
    assert public.error is True
    assert public.error_reason == "output_contract_violation"


def test_pack_domain_status_overrides_backend_transport_status() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["status", "manual_review_required"],
        }
    }
    response = BackendResponse(
        status="pass", summary="Extracted diagnoses",
        markdown='```json\n{"status":"REQUIRES_REVIEW","manual_review_required":true}\n```',
        backend_provider="test.provider.v1", backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent", run_id="run-status", trace_id="trace-status",
        runtime_mode="pure_llm", resp=response, include_trace=False,
        include_evidence=False, agent_pack=pack, t0=time.perf_counter(),
    )

    assert public.result["status"] == "REQUIRES_REVIEW"
    assert public.result["structured_extraction"]["valid"] is True


def test_completed_business_fail_is_not_a_runtime_error() -> None:
    """A rule/validation FAIL is a usable review result, not transport failure."""
    pack = {
        "manifest": {"human_review": "required"},
        "output_contract": {
            "schema_ref": "icoder/ComplianceReview/v1",
            "required_fields": [
                "review_conclusion", "issues_found", "manual_review_required",
            ],
        },
    }
    response = BackendResponse(
        status="fail",
        summary="Missing primary diagnosis",
        markdown=(
            '```json\n{"review_conclusion":"FAIL","issues_found":'
            '[{"severity":"critical"}],"manual_review_required":true}\n```'
        ),
        finish_state="completed",
        backend_provider="icoder.rule-engine.v1",
        backend_type="rule_engine",
    )

    public = _map_backend_response(
        agent_id="compliance-guardrail-agent",
        run_id="run-business-fail",
        trace_id="trace-business-fail",
        runtime_mode="rule_engine",
        resp=response,
        include_trace=True,
        include_evidence=False,
        agent_pack=pack,
        t0=time.perf_counter(),
    )

    assert public.result["review_conclusion"] == "FAIL"
    assert public.error is False
    assert public.error_reason == ""
    assert public.trace_events[0]["status"] == "ok"


def test_pack_required_human_review_cannot_be_disabled_by_model() -> None:
    pack = {
        "manifest": {"human_review": "required"},
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision", "manual_review_required"],
        },
    }
    response = BackendResponse(
        status="pass", summary="Model attempted auto approval",
        markdown='```json\n{"decision":"pass","manual_review_required":false}\n```',
        backend_provider="test.provider.v1", backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent", run_id="run-review", trace_id="trace-review",
        runtime_mode="pure_llm", resp=response, include_trace=False,
        include_evidence=False, agent_pack=pack, t0=time.perf_counter(),
    )

    assert public.result["manual_review_required"] is True
    assert public.manual_review_required is True
    assert public.result["structured_extraction"]["valid"] is True


def test_missing_documentation_forces_optional_pack_review() -> None:
    pack = {
        "manifest": {"human_review": "optional"},
        "output_contract": {
            "schema_ref": "icoder/NoteCompletenessOutput/v1",
            "required_fields": [
                "review_conclusion", "documentation_gaps", "completeness_score",
                "missing_sections", "present_sections", "required_sections",
            ],
        },
    }
    response = BackendResponse(
        status="pass",
        summary="Incomplete note",
        markdown=(
            '```json\n{"review_conclusion":"FAIL","documentation_gaps":'
            '[{"section":"既往史"}],"completeness_score":0.5,'
            '"missing_sections":["既往史"],"present_sections":["主诉"],'
            '"required_sections":["主诉","既往史"]}\n```'
        ),
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="note-completeness-agent", run_id="run-missing-note",
        trace_id="trace-missing-note", runtime_mode="pure_llm",
        resp=response, include_trace=False, include_evidence=False,
        agent_pack=pack, t0=time.perf_counter(),
    )

    assert public.manual_review_required is True
    assert public.result["manual_review_required"] is True


def test_no_confirmed_diagnosis_cannot_leak_rejected_code() -> None:
    raw_schema = {
        "review_conclusion": "FAIL",
        "primary_diagnosis": {
            "code": "J18.900", "description": "肺炎", "confidence": 0.3,
            "evidence": ["入院时考虑肺炎，后复查已排除"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [{
            "severity": "critical", "code": "NO_CONFIRMED_DIAGNOSIS",
            "message": "无确诊诊断", "suggestion": "补充记录",
        }],
        "manual_review_required": True,
    }
    result = CodingResult(
        codes=[CodingResultCode(
            code="J18.900", system="ICD-10-CN", display="肺炎",
            type="primary_diagnosis", confidence=0.3,
            evidence="入院时考虑肺炎，后复查已排除",
        )],
        summary="无确诊诊断", runtime_mode="corti_like_fast",
        raw_schema=raw_schema,
    )

    public = _map_coding_result(
        agent_id="medical-coding-agent", run_id="run-negated",
        trace_id="trace-negated", result=result, include_trace=False,
        include_evidence=True, t0=time.perf_counter(),
    )

    assert public.result["code_assignment"]["primary_diagnosis"]["code"] == ""
    assert public.result["codes"] == []
    assert public.evidence == []
    assert public.result["uncodable_items"][0]["item_type"] == "negated_finding"
    assert public.result["documentation_analysis"]["negated_findings"] == []
    assert public.result["manual_review_required"] is True
    assert public.error is False


def test_source_negation_is_uncodable_without_model_candidate() -> None:
    source = (
        "出院记录：入院时考虑肺炎，后经复查已排除；"
        "未形成其他确诊诊断，未实施手术。"
    )
    result = CodingResult(
        codes=[],
        summary="未生成编码候选",
        runtime_mode="corti_like_fast",
        raw_schema={
            "review_conclusion": "FAIL",
            "primary_diagnosis": {},
            "secondary_diagnoses": [],
            "procedures": [],
            "issues_found": [],
            "manual_review_required": True,
        },
    )

    public = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-source-negated",
        trace_id="trace-source-negated",
        result=result,
        include_trace=False,
        include_evidence=True,
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is False
    assert public.result["code_assignment"]["primary_diagnosis"]["code"] == ""
    assert public.result["uncodable_items"]
    assert all(
        item["item_type"] == "negated_finding"
        for item in public.result["uncodable_items"]
    )
    findings = public.result["documentation_analysis"]["negated_findings"]
    assert findings
    assert all(
        source[item["char_start"]:item["char_end"]] == item["text"]
        for item in findings
    )


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_failed_diagnosis_cannot_depend_on_provider_rule_or_severity(severity) -> None:
    raw_schema = {
        "review_conclusion": "FAIL",
        "primary_diagnosis": {
            "code": "J18.900", "description": "肺炎", "confidence": 0.3,
            "evidence": ["肺炎已排除"],
        },
        "issues_found": [{
            "severity": severity, "code": "RULE-001",
            "message": "无确诊诊断", "suggestion": "补充记录",
        }],
        "manual_review_required": True,
    }
    result = CodingResult(
        codes=[CodingResultCode(
            code="J18.900", system="ICD-10-CN", display="肺炎",
            type="primary_diagnosis", confidence=0.3, evidence="肺炎已排除",
        )],
        summary="无确诊诊断", runtime_mode="corti_like_fast",
        raw_schema=raw_schema,
    )

    public = _map_coding_result(
        agent_id="medical-coding-agent", run_id="run-rule-alias",
        trace_id="trace-rule-alias", result=result, include_trace=False,
        include_evidence=True, t0=time.perf_counter(),
    )

    assert public.result["code_assignment"]["primary_diagnosis"]["code"] == ""
    assert public.result["codes"] == []
    assert public.result["uncodable_items"]


def _current_medical_coding_pack() -> dict:
    path = (
        Path(__file__).resolve().parents[4]
        / "official_agents"
        / "medical_coding"
        / "agent_pack.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _span_grounded_medical_result(*, confidence: float = 0.94) -> tuple[CodingResult, str]:
    source = "DEID: \u533b\u751f\u660e\u786e\u8bb0\u5f55\u6025\u6027\u5de6\u5fc3\u8870\u7aed\u548c\u9ad8\u8840\u538b\u75c5\u3002"
    quote = "\u6025\u6027\u5de6\u5fc3\u8870\u7aed"
    start = source.index(quote)
    span = {
        "text": quote,
        "char_start": start,
        "char_end": start + len(quote),
        "doc_id": "input",
        "doc_type": "",
        "confidence": confidence,
    }
    raw_schema = {
        "review_conclusion": "WARNING",
        "primary_diagnosis": {
            "code": "I50.1",
            "description": quote,
            "confidence": 0.94,
            "category": "principal",
            "evidence": [span],
        },
        "secondary_diagnoses": [],
        "procedures": [],
        "extracted_diagnoses": [{
            "disease_text": quote,
            "supporting_evidence": [span],
        }],
        "issues_found": [],
        "manual_review_required": True,
    }
    return CodingResult(
        codes=[CodingResultCode(
            code="I50.1",
            system="ICD-10-CN",
            display=quote,
            type="primary_diagnosis",
            confidence=0.94,
            evidence=quote,
        )],
        summary="Coding review required",
        runtime_mode="corti_like_fast",
        raw_schema=raw_schema,
    ), source


def test_medical_primary_diagnosis_accepts_grounded_span_evidence() -> None:
    result, source = _span_grounded_medical_result()

    public = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-grounded-primary",
        trace_id="trace-grounded-primary",
        result=result,
        include_trace=True,
        include_evidence=True,
        agent_pack=_current_medical_coding_pack(),
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is False
    evidence = public.result["code_assignment"]["primary_diagnosis"]["evidence"][0]
    assert evidence["text"] == "\u6025\u6027\u5de6\u5fc3\u8870\u7aed"
    assert evidence["doc_id"] == "input"


def test_medical_v8_forces_nested_manual_review_for_clean_provider_output() -> None:
    result, source = _span_grounded_medical_result()
    result.raw_schema["manual_review_required"] = False

    public = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-clean-review-policy",
        trace_id="trace-clean-review-policy",
        result=result,
        include_trace=True,
        include_evidence=True,
        agent_pack=_current_medical_coding_pack(),
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is False
    assert public.manual_review_required is True
    assert public.result["validation_summary"]["manual_review_required"] is True
    assert public.result["human_review"]["review_required"] is True


def test_medical_runtime_error_suppresses_optimistic_default_payload() -> None:
    result = CodingResult(
        codes=[],
        summary="Medical coding inference did not complete.",
        runtime_mode="corti_like_fast",
        error=True,
        error_reason="schema_returned_error",
        raw_schema={
            "review_conclusion": "PASS",
            "manual_review_required": False,
        },
    )

    public = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-failed-coding",
        trace_id="trace-failed-coding",
        result=result,
        include_trace=True,
        include_evidence=True,
        agent_pack=_current_medical_coding_pack(),
        source_text="去标识病历",
        t0=time.perf_counter(),
    )

    assert public.error is True
    assert public.error_reason == "schema_returned_error"
    assert public.manual_review_required is True
    assert public.result == {"contract_output_suppressed": True}
    assert public.evidence == []
    assert public.warnings == []
    assert "PASS" not in repr(public.result)


def test_medical_contract_failure_trace_contains_only_safe_paths_and_counts() -> None:
    result, source = _span_grounded_medical_result(confidence=1.5)

    public = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-invalid-primary",
        trace_id="trace-invalid-primary",
        result=result,
        include_trace=True,
        include_evidence=True,
        agent_pack=_current_medical_coding_pack(),
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is True
    event = public.trace_events[-1]
    assert event["step"] == "contract_validation"
    assert event["status"] == "failed"
    metadata = event["metadata"]
    assert metadata["invalid_field_schema_count"] >= 1
    assert any("confidence" in path for path in metadata["invalid_paths"])
    assert source not in repr(metadata)


def test_generic_projection_repairs_unique_exact_evidence_span() -> None:
    source = "prefix acute heart failure suffix"
    quote = "acute heart failure"
    pack = {
        "manifest": {"human_review": "required"},
        "output_contract": {
            "schema_ref": "icoder/TestEvidenceOutput/v1",
            "required_fields": ["diagnoses", "manual_review_required"],
            "field_types": {
                "diagnoses": "array",
                "manual_review_required": "boolean",
            },
            "field_schemas": {
                "diagnoses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "evidence_text": {"type": "string"},
                            "char_span": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "minItems": 2,
                                "maxItems": 2,
                            },
                        },
                        "required": ["evidence_text", "char_span"],
                        "additionalProperties": False,
                    },
                },
                "manual_review_required": {"type": "boolean", "const": True},
            },
            "evidence_bindings": [{
                "id": "diagnosis_evidence_matches_input",
                "for_each": "diagnoses",
                "text_path": "evidence_text",
                "span_path": "char_span",
            }],
        },
    }
    response = BackendResponse(
        status="pass",
        summary="Done",
        markdown=(
            '```json\n{"diagnoses":[{"evidence_text":"acute heart failure",'
            '"char_span":[0,1]}],"manual_review_required":false}\n```'
        ),
        backend_provider="test.provider.v1",
        backend_type="llm_with_tools",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-ground-evidence",
        trace_id="trace-ground-evidence",
        runtime_mode="a2a_llm_with_tools",
        resp=response,
        include_trace=True,
        include_evidence=True,
        agent_pack=pack,
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is False
    assert public.result["diagnoses"][0]["char_span"] == [
        source.index(quote),
        source.index(quote) + len(quote),
    ]


def test_generic_contract_failure_trace_contains_only_paths_and_counts() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestOutput/v1",
            "required_fields": ["decision"],
            "field_types": {"decision": "boolean"},
        },
    }
    response = BackendResponse(
        status="pass",
        summary="Done",
        markdown='```json\n{"decision":"private-value"}\n```',
        backend_provider="test.provider.v1",
        backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent",
        run_id="run-safe-contract-trace",
        trace_id="trace-safe-contract-trace",
        runtime_mode="pure_llm",
        resp=response,
        include_trace=True,
        include_evidence=False,
        agent_pack=pack,
        source_text="private-source-text",
        t0=time.perf_counter(),
    )

    assert public.error is True
    event = public.trace_events[-2]
    assert event["step"] == "contract_validation"
    assert event["status"] == "failed"
    assert event["metadata"]["invalid_field_type_count"] == 1
    assert event["metadata"]["invalid_paths"] == ["decision"]
    assert "private-value" not in repr(event)
    assert "private-source-text" not in repr(event)
    assert public.trace_events[-1]["status"] == "failed"


def test_runtime_injects_authoritative_trace_refs_for_pack_contract() -> None:
    pack = {
        "output_contract": {
            "schema_ref": "icoder/TestAgentOutput/v1",
            "required_fields": ["decision", "trace_refs"],
        },
    }
    response = BackendResponse(
        status="pass", summary="Done",
        markdown='```json\n{"decision":"review"}\n```',
        trace_refs=["provider-trace-1"],
        backend_provider="test.provider.v1", backend_type="pure_llm",
    )

    public = _map_backend_response(
        agent_id="test-agent", run_id="run-authoritative",
        trace_id="trace-authoritative", runtime_mode="pure_llm",
        resp=response, include_trace=False, include_evidence=False,
        agent_pack=pack, t0=time.perf_counter(),
    )

    assert public.result["trace_refs"] == {
        "run_id": "run-authoritative",
        "trace_id": "trace-authoritative",
        "provider_trace_refs": ["provider-trace-1"],
    }
    assert public.result["structured_extraction"]["valid"] is True


def test_diagnosis_projection_omits_unverified_code_without_inventing_one() -> None:
    """A safe provider refusal is reviewable output, not a contract crash."""
    official_agents = Path(__file__).resolve().parents[4] / "official_agents"
    pack = json.loads(
        (official_agents / "diagnosis-extractor" / "agent_pack.json").read_text(
            encoding="utf-8"
        )
    )
    source = "合成病例：胸痛，未记录明确诊断。"
    provider_payload = {
        "status": "WARNING",
        "diagnoses": [{
            "diagnosis_text": "未验证诊断候选",
            "evidence_text": "胸痛",
            "char_span": [5, 7],
            "assertion_status": "present",
            "icd10_cn_code": "",
            "icd10_cn_name": "",
            "confidence": "low",
            "verification": "tool_unavailable",
        }],
        "non_codable_mentions": [],
        "issues_found": [],
        "manual_review_required": True,
    }
    response = BackendResponse(
        status="incomplete",
        summary="Synthetic safe refusal",
        markdown=f"```json\n{json.dumps(provider_payload, ensure_ascii=False)}\n```",
        backend_provider="icoder.llm-with-tools.v1",
        backend_type="llm_with_tools",
    )

    public = _map_backend_response(
        agent_id="diagnosis-extractor",
        run_id="run-dx-unverified",
        trace_id="trace-dx-unverified",
        runtime_mode="a2a_llm_with_tools",
        resp=response,
        include_trace=True,
        include_evidence=True,
        agent_pack=pack,
        source_text=source,
        t0=time.perf_counter(),
    )

    assert public.error is False
    assert public.manual_review_required is True
    assert public.result["status"] == "REQUIRES_REVIEW"
    assert public.result["diagnoses"] == []
    assert public.result["structured_extraction"]["valid"] is True
    assert "unverified diagnosis" in " ".join(
        public.result["structured_extraction"]["warnings"]
    )
    assert "未验证诊断候选" not in repr(
        public.result["structured_extraction"]["warnings"]
    )
    assert "icd10_cn_code" not in repr(public.result["issues_found"])
