from __future__ import annotations

import pytest

from app.coding_runtime.base import CodingResult
from app.icoder.agent_runtime.a2a_facade import (
    build_medical_coding_inbound_response,
    medical_coding_pack,
    medical_coding_schema_ref,
)
from app.services.result_attestation import verify_result_attestation
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


def _result(*, error: bool = False) -> CodingResult:
    return CodingResult(
        codes=[],
        runtime_mode="corti_like_fast",
        latency_ms=7,
        llm_provider="mock",
        trace_id="trace-medical-a2a",
        run_id="run-medical-a2a",
        raw_schema=MedicalCodingOutputSchema(
            review_conclusion="WARNING",
            manual_review_required=True,
            confidence=0.0,
            provider="mock",
            model="mock",
        ).to_dict(),
        trace_events=[],
        error=error,
        error_reason="test_failure" if error else "",
    )


def test_builder_publishes_exact_current_pack_domain_and_attestation(monkeypatch):
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )
    response = build_medical_coding_inbound_response(
        result=_result(),
        run_id="run-medical-a2a",
        trace_id="trace-medical-a2a",
        context_id="context-medical-a2a",
        organization_id="org-medical-a2a",
    )

    assert response.kind == "message"
    data_part = response.parts[0]
    data = data_part["data"]
    pack = medical_coding_pack()
    assert set(data) == set(pack["output_contract"]["required_fields"])
    assert "_runtime" not in data
    assert "markdown" not in data
    assert data_part["metadata"]["schema_ref"] == medical_coding_schema_ref()
    assert data_part["metadata"]["runtime"]["runtime_mode"] == "corti_like_fast"
    assert isinstance(data_part["metadata"]["rendered_markdown"], str)

    token = data_part["metadata"]["result_attestation"]
    verified = verify_result_attestation(
        token,
        expected_run_id="run-medical-a2a",
        expected_agent_id="medical-coding-agent",
        expected_schema_ref=medical_coding_schema_ref(),
        expected_organization_id="org-medical-a2a",
        result=data,
    )
    assert verified.run_id == "run-medical-a2a"


def test_builder_fails_closed_on_provider_error(monkeypatch):
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )
    response = build_medical_coding_inbound_response(
        result=_result(error=True),
        run_id="run-medical-a2a",
        trace_id="trace-medical-a2a",
        context_id="context-medical-a2a",
    )

    assert response.kind == "error"
    assert response.http_status == 503
    assert response.error["code"] == "PROVIDER_EXECUTION_FAILED"
    assert response.metadata["manual_review_required"] is True


def test_builder_fails_closed_on_nested_contract_violation(monkeypatch):
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    from official_agents.medical_coding.schema import MedicalCodingAgentOutputV2

    original = MedicalCodingAgentOutputV2.to_dict

    def invalid_to_dict(self):
        payload = original(self)
        payload["human_review"] = {"review_required": "not-a-boolean"}
        return payload

    monkeypatch.setattr(MedicalCodingAgentOutputV2, "to_dict", invalid_to_dict)
    response = build_medical_coding_inbound_response(
        result=_result(),
        run_id="run-medical-a2a",
        trace_id="trace-medical-a2a",
        context_id="context-medical-a2a",
    )

    assert response.kind == "error"
    assert response.http_status == 503
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["invalid_field_schemas"]


@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low"])
def test_a2a_failed_review_withholds_diagnoses_independent_of_severity(monkeypatch, severity):
    monkeypatch.setenv("ICODER_RESULT_ATTESTATION_KEY", "test-only-attestation-key-32-bytes-minimum")
    result = _result()
    result.raw_schema.update({
        "review_conclusion": "FAIL",
        "primary_diagnosis": {
            "code": "J18.900", "description": "肺炎", "confidence": 0.3,
            "evidence": ["肺炎已排除"],
        },
        "secondary_diagnoses": [{
            "code": "J18.9", "description": "肺炎", "evidence": ["肺炎已排除"],
        }],
        "issues_found": [{"severity": severity, "code": "EVIDENCE_INSUFFICIENT", "message": "无确诊诊断"}],
    })
    response = build_medical_coding_inbound_response(
        result=result, run_id="run-medical-a2a", trace_id="trace-medical-a2a",
        context_id="context-medical-a2a", source_text="肺炎已排除",
    )
    assert response.kind == "message"
    data = response.parts[0]["data"]
    assert data["code_assignment"]["primary_diagnosis"]["code"] == ""
    assert data["code_assignment"]["secondary_diagnoses"] == []
    assert len(data["uncodable_items"]) == 2
    assert data["validation_summary"]["passed"] is False
    assert data["human_review"]["review_required"] is True
    # Projection does not destroy the internal evidence used for audit.
    assert result.raw_schema["primary_diagnosis"]["code"] == "J18.900"
