from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


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
            },
        },
    }


def test_governed_discharge_education_a2a_is_grounded_and_review_only() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = (
        "出院诊断：慢性心力衰竭\n检验结果：血钾4.1mmol/L\n"
        "出院用药：呋塞米20mg，每日一次\n复诊计划：7日后心内科复诊\n"
        "警示症状：呼吸困难加重时按出院医嘱及时就医\n"
        "生活方式：低盐饮食；每日晨起称重"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/discharge-edu/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "discharge-education-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["education_status"] == "COMPLETED"
    assert data["diagnosis_summary"] == "慢性心力衰竭"
    assert data["medication_instructions"] == "呋塞米20mg，每日一次"
    assert data["translation_status"] == "VERBATIM_DOCUMENTED_CONTENT_ONLY"
    assert data["external_knowledge_used"] is False
    assert data["clinical_interpretation_performed"] is False
    assert data["clinical_recommendations_generated"] is False
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == (
        "icoder/DischargeEducationOutput/v3"
    )
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-discharge-education.v1"
    )


def test_governed_discharge_education_a2a_fails_closed_without_labels() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/discharge-edu/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "患者因心衰出院，继续呋塞米并于一周后复诊。",
                "discharge-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["education_status"] == "INPUT_REQUIRED"
    assert data["diagnosis_summary"] == ""
    assert data["medication_instructions"] == ""
    assert data["follow_up"] == ""
    assert data["evidence_items"] == []
    assert data["manual_review_required"] is True
