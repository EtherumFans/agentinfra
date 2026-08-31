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


def test_governed_discharge_summary_a2a_is_grounded_and_review_only() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = (
        "出院诊断：\n1. 慢性心力衰竭\n2. 原发性高血压\n"
        "手术及操作：冠状动脉造影\n"
        "诊疗经过：完成检查并按原记录治疗，症状好转。\n"
        "出院用药：呋塞米20mg，每日一次\n"
        "随访计划：7日后心内科复诊\n出院状态：好转"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/discharge-summary-structuring/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "discharge-summary-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["structuring_status"] == "COMPLETED"
    assert data["diagnoses"][0]["text"] == "慢性心力衰竭"
    assert data["procedures"][0]["text"] == "冠状动脉造影"
    assert data["discharge_status"]["normalized_status"] == "IMPROVED"
    assert data["summary_generation_status"] == (
        "VERBATIM_SECTION_REORGANIZATION_ONLY"
    )
    assert data["icd_codes_assigned"] is False
    assert data["medication_reconciliation_performed"] is False
    assert data["clinical_inference_performed"] is False
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == (
        "icoder/DischargeSummaryStructured/v5"
    )
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-discharge-summary.v1"
    )


def test_governed_discharge_summary_a2a_fails_closed_without_headings() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/discharge-summary-structuring/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "患者因心衰住院，治疗后好转出院并继续用药。",
                "discharge-summary-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["structuring_status"] == "INPUT_REQUIRED"
    assert data["diagnoses"] == []
    assert data["procedures"] == []
    assert data["discharge_orders"] == []
    assert data["evidence_items"] == []
    assert data["manual_review_required"] is True
