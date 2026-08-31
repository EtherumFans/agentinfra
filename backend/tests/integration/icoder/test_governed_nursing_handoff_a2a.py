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


def test_governed_nursing_handoff_a2a_is_grounded_and_review_only() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = (
        "患者：患者甲\n床位：12床\n主要问题：术后观察\n当前状态：清醒\n"
        "管路/设备：右颈内静脉置管在位\n待办：关注血培养结果\n"
        "安全/预防：跌倒风险评估待核验"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/nursing-handoff/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "nursing-handoff-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["handoff_status"] == "PARTIAL"
    assert data["patient_handoffs"][0]["patient_identifier"] == "患者甲"
    assert data["safety_risks"] == ["跌倒风险评估待核验"]
    assert data["clinical_priority_assessed"] is False
    assert data["medical_calculator_used"] is False
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0][
        "text"
    ]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/NursingHandoffOutput/v4"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-nursing-handoff.v1"
    )


def test_governed_nursing_handoff_a2a_fails_closed_without_sections() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/nursing-handoff/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("患者术后回病房，身份和管路状态未记录。", "handoff-input-required"),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["handoff_status"] == "INPUT_REQUIRED"
    assert data["patient_handoffs"] == []
    assert data["evidence_items"] == []
    assert data["manual_review_required"] is True
