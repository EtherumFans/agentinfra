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


def test_governed_icu_summary_a2a_is_grounded_and_review_only() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = (
        "入ICU原因：术后监护\n入院诊断：主动脉夹层术后\n"
        "器官支持：有创机械通气FiO2 40%\n生命体征：血压110/68mmHg\n"
        "检验结果：乳酸2.1mmol/L\n待办：血气分析待回报"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/icu-summary/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "icu-summary-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["summary_status"] == "PARTIAL"
    assert data["admission_reason"] == "术后监护"
    assert data["organ_support"][0]["detail"] == "有创机械通气FiO2 40%"
    assert data["clinical_scores_status"] == (
        "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED"
    )
    assert data["clinical_recommendations_generated"] is False
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/IcuSummaryOutput/v3"
    assert result["metadata"]["backend_provider"] == "icoder.governed-icu-summary.v1"


def test_governed_icu_summary_a2a_fails_closed_without_labels() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/icu-summary/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("患者术后转入 ICU，血压偏低。", "icu-input-required"),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["summary_status"] == "INPUT_REQUIRED"
    assert data["admission_diagnoses"] == []
    assert data["evidence_items"] == []
    assert data["manual_review_required"] is True
