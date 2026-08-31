"""Fail-closed public REST/A2A contracts for the CDI Agent."""

import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler
from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
)
from app.icoder.agent_runtime.cdi.domain import EvidenceSpan, ProviderQuery
from app.services.dedicated_project_policy import (
    DedicatedProjectPolicy,
    ProjectPolicyLLM,
)
from icoder_runtime.backends.output_contract_validation import PreparedSourceDocument


def _successful_case():
    trace_schema = CDIA2AHandler._output_contract()["field_schemas"]["trace_refs"]
    stage_keys = trace_schema["properties"]["stage_trace"]["required"]
    gate_keys = trace_schema["properties"]["gate_results"]["required"]
    return SimpleNamespace(
        case_id="CASE-TEST",
        completion_state="REVIEW_REQUIRED",
        encounter_summary=SimpleNamespace(
            key_points=[],
            encounter_metadata={
                "encounter_type": "inpatient",
                "patient_age": "unknown",
                "patient_sex": "unknown",
            },
        ),
        documentation_gaps=[],
        proposed_provider_queries=[],
        query_rewrite_queue=[],
        coding_specificity_checklist=[],
        risk_flags=[],
        specialist_trace=[],
        stage_run_ids={key: f"run-{index}" for index, key in enumerate(gate_keys)},
        stage_trace_ids={
            key: f"trace-{index}" for index, key in enumerate(stage_keys)
        },
        degraded_safety_gates={},
    )


def _install_successful_runtime(monkeypatch, *, case=None) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler

    class FakeRunner:
        def __init__(self):
            self.stage_traces = {}
            self.expert_traces = []

    class FakeOrchestrator:
        def __init__(self, *, runner):
            self.runner = runner

        def run(self, case):
            return case_result

    case_result = case or _successful_case()

    monkeypatch.setattr(cdi_a2a_handler, "RealCDIRunner", FakeRunner)
    monkeypatch.setattr(cdi_a2a_handler, "CDIOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PROVIDER", "deepseek")


def _install_rest_gate_degraded_runtime(monkeypatch, cdi_api):
    class FakeRunner:
        def __init__(self):
            self.stage_traces = {}
            self.expert_traces = []

    class FakeOrchestrator:
        def __init__(self, *, runner):
            self.runner = runner

        def run(self, case):
            case.degraded_safety_gates = {
                "claim_evidence_alignment_gate": "degraded_queries=1",
            }
            return case

    async def _unexpected_persist(*args, **kwargs):
        raise AssertionError("degraded CDI result must not be persisted")

    audit = AsyncMock()
    fake_db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    monkeypatch.setattr(cdi_api, "RealCDIRunner", FakeRunner)
    monkeypatch.setattr(cdi_api, "CDIOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cdi_api, "persist_case_to_db", _unexpected_persist)
    monkeypatch.setattr(cdi_api, "tenant_owned_system_audit", audit)
    monkeypatch.setattr(cdi_api.settings, "LLM_PROVIDER", "deepseek")
    return audit, fake_db


def test_mock_provider_returns_no_clinical_result(monkeypatch) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler

    captured = []
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(
        cdi_a2a_handler,
        "emit_trace_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )
    raw_phone = "13800138000"
    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": f"患者电话 {raw_phone}"}],
                interaction_id="msg-1",
                context_id="00000000-0000-4000-8000-000000000001",
            )
        ),
    )

    assert response.kind == "error"
    assert response.http_status == 503
    assert response.parts == []
    assert response.error["code"] == "PROVIDER_UNAVAILABLE"
    assert response.metadata["manual_review_required"] is True
    assert raw_phone not in response.redacted_input
    assert [args[1] for args, _ in captured] == [
        "user_message_received",
        "completion",
    ]
    assert captured[1][1]["status"] == "failed"
    assert captured[1][1]["safe_metadata"]["error_code"] == "PROVIDER_UNAVAILABLE"
    assert "<REDACTED:PHONE>" in response.redacted_input


def test_internal_project_policy_governs_cdi_runner_and_trace_without_leakage(
    monkeypatch,
) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler
    from app.services import llm_service as llm_service_module

    sentinel = "CDI_PROJECT_POLICY_SECRET_SENTINEL"
    digest = hashlib.sha256(sentinel.encode("utf-8")).hexdigest()
    policy = DedicatedProjectPolicy(
        instructions=sentinel,
        digest=digest,
        project_expert_ids=("expert-project-1",),
        prompt_overridden=True,
        source_experts_fixed=True,
    )
    prompts: list[str] = []
    trace_events = []
    received = {}

    class FakeLLM:
        async def chat(self, *, messages, system_prompt=None, **kwargs):
            prompts.append(str(system_prompt or ""))
            return {"content": "{}", "usage": {}}

    class FakeRunner:
        def __init__(self, *, llm):
            assert isinstance(llm, ProjectPolicyLLM)
            received["runner_llm"] = llm
            self.stage_traces = {}
            self.expert_traces = []

    class FakeOrchestrator:
        def __init__(self, *, runner, llm):
            assert llm is received["runner_llm"]
            self.llm = llm

        def run(self, case):
            asyncio.run(self.llm.chat(
                messages=[{"role": "user", "content": "synthetic chart"}],
                system_prompt="SOURCE CDI SAFETY PROMPT",
            ))
            return _successful_case()

    monkeypatch.setattr(cdi_a2a_handler, "RealCDIRunner", FakeRunner)
    monkeypatch.setattr(cdi_a2a_handler, "CDIOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_service_module, "llm_service", FakeLLM())
    monkeypatch.setattr(
        cdi_a2a_handler,
        "emit_trace_event",
        lambda *args, **kwargs: trace_events.append((args, kwargs)),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化合成病历。"}],
                context_id="00000000-0000-4000-8000-000000000010",
            ),
            metadata={
                "run_id": "run-cdi-project-policy",
                "organization_id": "org-cdi-project",
                "_dedicated_project_policy_token": policy,
            },
        ),
    )

    assert response.kind == "message", response.metadata
    assert prompts and prompts[0].startswith("SOURCE CDI SAFETY PROMPT")
    assert sentinel in prompts[0]
    assert "IMMUTABLE_CDI_BOUNDARY" in prompts[0]
    scope_metadata = trace_events[1][1]["safe_metadata"]
    assert trace_events[1][0][1] == "scope_checked"
    assert scope_metadata["project_policy_digest"] == digest
    assert scope_metadata["project_expert_ids"] == ["expert-project-1"]
    assert sentinel not in str(scope_metadata)
    assert sentinel not in str(response.metadata)
    assert sentinel not in str(response.parts)


def test_external_metadata_dict_cannot_spoof_cdi_project_policy(
    monkeypatch,
) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler

    _install_successful_runtime(monkeypatch)
    trace_events = []
    sentinel = "CLIENT_SPOOFED_CDI_POLICY_SENTINEL"
    monkeypatch.setattr(
        cdi_a2a_handler,
        "emit_trace_event",
        lambda *args, **kwargs: trace_events.append((args, kwargs)),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化合成病历。"}],
                context_id="00000000-0000-4000-8000-000000000011",
            ),
            metadata={
                "run_id": "run-cdi-spoofed-policy",
                "organization_id": "org-cdi-project",
                "_dedicated_project_policy_token": {
                    "instructions": sentinel,
                    "digest": "client-controlled",
                },
            },
        ),
    )

    assert response.kind == "message", response.metadata
    assert [args[1] for args, _ in trace_events] == [
        "user_message_received",
        "output_generated",
    ]
    assert sentinel not in str(response.metadata)
    assert sentinel not in str(response.parts)


def test_required_safety_gate_degradation_publishes_no_a2a_result(
    monkeypatch,
) -> None:
    case = _successful_case()
    case.degraded_safety_gates = {
        "semantic_necessity_gate": "degraded_queries=1",
    }
    _install_successful_runtime(monkeypatch, case=case)

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化病历。"}],
                interaction_id="msg-gate-degraded",
                context_id="00000000-0000-4000-8000-000000000004",
            )
        ),
    )

    assert response.kind == "error"
    assert response.http_status == 503
    assert response.parts == []
    assert response.error["code"] == "PROVIDER_EXECUTION_FAILED"
    assert response.metadata["degraded_safety_gates"] == [
        "semantic_necessity_gate",
    ]


def test_required_safety_gate_degradation_is_not_persisted_by_rest(
    monkeypatch,
) -> None:
    from app.api import cdi as cdi_api

    # Some legacy API test modules set this at import time. This contract must
    # exercise the production branch regardless of collection order.
    monkeypatch.delenv("ICODER_CDI_FORCE_STUB_FOR_TESTS", raising=False)

    audit, fake_db = _install_rest_gate_degraded_runtime(monkeypatch, cdi_api)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(cdi_api.run_cdi(
            cdi_api.CDIRunRequest(chart_excerpt="去标识化病历。"),
            current_user=SimpleNamespace(id="user-cdi"),
            current_org=SimpleNamespace(id="org-cdi"),
            db=fake_db,
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "provider_execution_failed"
    assert exc_info.value.detail["degraded_safety_gates"] == [
        "claim_evidence_alignment_gate",
    ]
    audit.assert_awaited_once()
    audit_kwargs = audit.await_args.kwargs
    assert audit_kwargs["action"] == "cdi.run.failed.required_gate_degraded"
    assert audit_kwargs["organization_id"] == "org-cdi"
    assert audit_kwargs["details"]["clinical_result_published"] is False
    fake_db.commit.assert_awaited_once()
    fake_db.rollback.assert_not_awaited()


def test_required_gate_audit_failure_still_publishes_no_rest_result(
    monkeypatch,
) -> None:
    from app.api import cdi as cdi_api

    monkeypatch.delenv("ICODER_CDI_FORCE_STUB_FOR_TESTS", raising=False)
    audit, fake_db = _install_rest_gate_degraded_runtime(monkeypatch, cdi_api)
    audit.side_effect = RuntimeError("audit unavailable")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(cdi_api.run_cdi(
            cdi_api.CDIRunRequest(chart_excerpt="去标识化病历。"),
            current_user=SimpleNamespace(id="user-cdi"),
            current_org=SimpleNamespace(id="org-cdi"),
            db=fake_db,
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "audit_persistence_failed"
    fake_db.commit.assert_not_awaited()
    fake_db.rollback.assert_awaited_once()


def test_success_publishes_exact_current_pack_contract_and_attestation(
    monkeypatch,
) -> None:
    from app.services.result_attestation import verify_result_attestation

    _install_successful_runtime(monkeypatch)
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )
    request = InboundRequest(
        message=InboundMessage(
            parts=[{"kind": "text", "text": "去标识化病历，未发现文档缺口。"}],
            interaction_id="msg-success",
            context_id="00000000-0000-4000-8000-000000000002",
        ),
        metadata={
            "run_id": "run-cdi-current-contract",
            "organization_id": "org-cdi-test",
        },
    )

    response = CDIA2AHandler().handle(CDIA2AHandler.AGENT_ID, request)

    assert response.kind == "message", response.metadata
    data_part = response.parts[0]
    data = data_part["data"]
    contract = CDIA2AHandler._output_contract()
    assert set(data) == set(contract["required_fields"])
    assert "case_id" not in data
    assert "stage_traces" not in data
    assert "manual_review_required" not in data
    assert data["human_review"]["cdi_specialist_review_required"] is True
    assert data["human_review"]["clinician_response_required"] is True
    assert response.metadata["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == contract["schema_ref"]
    claims = verify_result_attestation(
        data_part["metadata"]["result_attestation"],
        expected_run_id="run-cdi-current-contract",
        expected_agent_id=CDIA2AHandler.AGENT_ID,
        expected_schema_ref=contract["schema_ref"],
        expected_organization_id="org-cdi-test",
        result=data,
    )
    assert claims.run_id == "run-cdi-current-contract"


def test_internal_privacy_counters_do_not_break_public_gate_contract(
    monkeypatch,
) -> None:
    case = _successful_case()
    case.stage_run_ids.update({
        "encounter_synthesis::ungrounded_removed": "2",
        "specialist_trace_emit::quantity_redacted": "1",
    })
    _install_successful_runtime(monkeypatch, case=case)
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化病历。"}],
                context_id="00000000-0000-4000-8000-000000000013",
            ),
            metadata={"run_id": "run-cdi-private-counter"},
        ),
    )

    assert response.kind == "message", response.metadata
    gate_results = response.parts[0]["data"]["trace_refs"]["gate_results"]
    assert "encounter_synthesis::ungrounded_removed" not in gate_results
    assert "specialist_trace_emit::quantity_redacted" not in gate_results


def test_missing_model_demographics_are_projected_as_unknown(monkeypatch) -> None:
    case = _successful_case()
    case.encounter_summary.encounter_metadata = {
        "encounter_type": "inpatient",
        "model_added_field": "must not be public",
    }
    _install_successful_runtime(monkeypatch, case=case)
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化病历，未提供人口学信息。"}],
                context_id="00000000-0000-4000-8000-000000000012",
            ),
            metadata={
                "run_id": "run-cdi-missing-demographics",
                "organization_id": "org-cdi-test",
            },
        ),
    )

    assert response.kind == "message", response.metadata
    metadata = response.parts[0]["data"]["encounter_summary"][
        "encounter_metadata"
    ]
    assert metadata == {
        "patient_age": "unknown",
        "patient_sex": "unknown",
        "encounter_type": "inpatient",
    }


def test_success_emits_attributed_cdi_provider_telemetry(monkeypatch) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler
    from app.icoder.agent_runtime.cdi.real_runner import StageTrace

    class FakeRunner:
        def __init__(self):
            self.stage_traces = {
                "encounter_synthesis": StageTrace(
                    stage="encounter_synthesis",
                    provider="deepseek",
                    model="deepseek-chat",
                    latency_ms=8,
                    prompt_tokens=6,
                    completion_tokens=2,
                    total_tokens=8,
                )
            }
            self.expert_traces = []

    class FakeOrchestrator:
        def __init__(self, *, runner):
            self.runner = runner

        def run(self, case):
            return _successful_case()

    captured = []
    monkeypatch.setattr(cdi_a2a_handler, "RealCDIRunner", FakeRunner)
    monkeypatch.setattr(cdi_a2a_handler, "CDIOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PRICE_INPUT_PER_1M", 1.0)
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PRICE_OUTPUT_PER_1M", 2.0)
    monkeypatch.setattr(
        cdi_a2a_handler,
        "emit_trace_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    response = CDIA2AHandler().handle(
        CDIA2AHandler.AGENT_ID,
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": "去标识化病历。"}],
                interaction_id="msg-cdi-telemetry",
                context_id="00000000-0000-4000-8000-000000000009",
            ),
            metadata={
                "run_id": "run-cdi-telemetry",
                "trace_id": "trace-cdi-telemetry",
                "organization_id": "org-cdi-telemetry",
                "user_id": "user-cdi-telemetry",
            },
        ),
    )

    assert response.kind == "message"
    assert response.metadata["cost"] == {
        "amount": 0.00001,
        "currency": "CNY",
        "source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }
    assert len(captured) == 2
    start_args, start_kwargs = captured[0]
    assert start_args == ("run-cdi-telemetry", "user_message_received")
    assert start_kwargs["safe_metadata"]["_trace_id"] == "trace-cdi-telemetry"
    args, kwargs = captured[1]
    assert args == ("run-cdi-telemetry", "output_generated")
    assert kwargs["status"] == "ok"
    metadata = kwargs["safe_metadata"]
    assert metadata["backend_type"] == "cdi_orchestrator"
    assert metadata["model_provider"] == "deepseek"
    assert metadata["model_name"] == "deepseek-chat"
    assert metadata["total_tokens"] == 8
    assert metadata["llm_call_count"] == 1
    assert metadata["cost_amount"] == 0.00001
    assert metadata["cost_currency"] == "CNY"
    assert metadata["cost_source"] == "configured_usage_pricing_estimate"
    assert metadata["billing_authoritative"] is False
    assert metadata["_trace_id"] == "trace-cdi-telemetry"
    assert metadata["_organization_id"] == "org-cdi-telemetry"


def test_nested_contract_violation_fails_closed(monkeypatch) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler

    _install_successful_runtime(monkeypatch)
    captured = []
    monkeypatch.setattr(
        cdi_a2a_handler,
        "emit_trace_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )
    monkeypatch.setattr(
        CDIA2AHandler,
        "_query_gate_summary",
        staticmethod(
            lambda queue, provider_query_count=0: {"withheld_count": "invalid"}
        ),
    )
    request = InboundRequest(
        message=InboundMessage(
            parts=[{"kind": "text", "text": "去标识化病历。"}],
            interaction_id="msg-invalid",
            context_id="00000000-0000-4000-8000-000000000003",
        ),
        metadata={"run_id": "run-cdi-invalid"},
    )

    response = CDIA2AHandler().handle(CDIA2AHandler.AGENT_ID, request)

    assert response.kind == "error"
    assert response.http_status == 503
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["invalid_field_schemas"]
    args, kwargs = captured[-1]
    assert args[1] == "contract_validation"
    assert kwargs["status"] == "failed"
    safe_metadata = kwargs["safe_metadata"]
    assert safe_metadata["error_code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert safe_metadata["invalid_field_schema_count"] > 0
    assert safe_metadata["invalid_paths"]
    assert "actual" not in safe_metadata
    assert "expected" not in safe_metadata


def test_public_query_projection_keeps_all_evidence_spans() -> None:
    query = ProviderQuery(
        query_id="q1",
        gap_id="g1",
        topic="conflict",
        reason="two chart locations differ",
        evidence_span=EvidenceSpan(document_id="d", quote="first fact"),
        evidence_spans=[
            EvidenceSpan(document_id="d", quote="first fact", char_start=0, char_end=10),
            EvidenceSpan(document_id="d", quote="second fact", char_start=20, char_end=31),
        ],
        query_text="Please clarify the documented conflict.",
    )

    projected = CDIA2AHandler._query_dict(query)

    assert [span["quote"] for span in projected["evidence_spans"]] == [
        "first fact",
        "second fact",
    ]
    assert projected["evidence_span"]["quote"] == "first fact"


def test_public_gate_summary_does_not_expose_rejected_draft_text() -> None:
    queue = [
        {
            "status": "NEEDS_QUERY_DRAFT",
            "query_text": "internal draft",
            "gate_reasons": ["internal reason"],
        },
        {"status": "NEEDS_CDI_REWRITE", "query_text": "compound draft"},
    ]

    summary = CDIA2AHandler._query_gate_summary(queue)

    assert summary == {
        "withheld_count": 2,
        "status_counts": {"REWRITE_CANDIDATE_GENERATED": 0},
        "manual_cdi_action_required": True,
    }
    assert "internal draft" not in str(summary)


def test_public_gate_summary_requires_action_for_publishable_drafts() -> None:
    summary = CDIA2AHandler._query_gate_summary([], provider_query_count=1)

    assert summary == {
        "withheld_count": 0,
        "status_counts": {"REWRITE_CANDIDATE_GENERATED": 0},
        "manual_cdi_action_required": True,
    }


def test_multidocument_global_span_is_rebased_to_document_coordinates() -> None:
    documents = [
        PreparedSourceDocument(document_id="admission", text="alpha finding"),
        PreparedSourceDocument(document_id="progress", text="beta finding"),
    ]
    bundle, segments = CDIA2AHandler._document_bundle(documents)
    global_start = bundle.index("beta")
    span = EvidenceSpan(
        document_id="chart-001",
        quote="beta",
        char_start=global_start,
        char_end=global_start + 4,
    )

    projected = CDIA2AHandler._span(span, segments)

    assert projected == {
        "document_id": "progress",
        "quote": "beta",
        "char_start": 0,
        "char_end": 4,
        "documented_at": "",
    }
