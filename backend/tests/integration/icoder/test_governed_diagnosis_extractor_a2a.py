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


def test_governed_diagnosis_extractor_a2a_returns_evidence_bound_cn_candidate() -> None:
    from app.main import app

    text = (
        "出院诊断：急性前壁心肌梗死。既往有高血压病史。"
        "请提取本次诊断并给出 ICD-10-CN 候选。"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/diagnosis-extractor/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "diagnosis-extractor-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["status"] == "WARNING"
    assert data["diagnoses"][0]["icd10_cn_code"] == "I21.001"
    assert data["diagnoses"][0]["char_span"] == [5, 13]
    assert data["non_codable_mentions"][0]["assertion_status"] == "history_of"
    assert data["non_codable_mentions"][0]["char_span"] == [14, 22]
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == "icoder/DiagnosisExtractionOutput/v7"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-diagnosis-extractor.v1"
    )


def test_governed_diagnosis_extractor_a2a_does_not_promote_negated_entities() -> None:
    from app.main import app

    text = "病程记录：考虑肺炎，复查后已排除肺炎；否认糖尿病史。"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/diagnosis-extractor/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "diagnosis-extractor-negated-a2a"),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["status"] == "REQUIRES_REVIEW"
    assert data["diagnoses"] == []
    assert {item["assertion_status"] for item in data["non_codable_mentions"]} == {
        "suspected", "negated",
    }
