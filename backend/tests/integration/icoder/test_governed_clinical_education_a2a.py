from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "official_agents"
    / "clinical-education"
    / "agent_pack.json"
)


def _payload(text: str, request_id: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": text}],
                "metadata": {},
            }
        },
    }


def test_governed_clinical_education_a2a_is_source_bound_and_review_only() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/clinical-education/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "clinical-education-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["education_status"] == "READY_FOR_REVIEW"
    assert data["approved_source"]["approval_status"]["documented_text"] == "已批准"
    assert data["source_statements"][0]["documented_text"] in text
    assert data["content_generation_status"] == "SOURCE_BOUND_TEMPLATE_ONLY"
    assert data["question_classification_performed"] is False
    assert data["clinical_reasoning_performed"] is False
    assert data["diagnostic_advice_generated"] is False
    assert data["treatment_advice_generated"] is False
    assert data["drug_interaction_assessed"] is False
    assert data["medical_calculator_used"] is False
    assert data["pubmed_lookup_performed"] is False
    assert data["web_search_performed"] is False
    assert data["external_knowledge_used"] is False
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/ClinicalEducationOutput/v6"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-clinical-education.v1"
    )


def test_governed_clinical_education_a2a_fails_closed_without_source() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/clinical-education/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "请给出脓毒症鉴别诊断、机制和抗菌药物方案。",
                "clinical-education-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["education_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["source_statements"] == []
    assert data["learning_objectives"] == []
    assert data["knowledge_checks"] == []
    assert data["production_writeback_blocked"] is True
