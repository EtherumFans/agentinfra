from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_governed_evidence_extractor_a2a_returns_same_local_contract() -> None:
    from app.main import app

    payload = {
        "jsonrpc": "2.0",
        "id": "evidence-extractor-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{
                    "kind": "text",
                    "text": "待核查编码：N18.803。\n病历文本：慢性肾脏病3期。",
                }],
                "metadata": {},
            },
        },
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/evidence-extractor/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["extraction_status"] == "COMPLETED"
    assert data["input_codes"] == ["N18.803"]
    assert data["located_mentions"][0]["evidence_text"] == "慢性肾脏病3期"
    assert data["located_mentions"][0]["clinical_support_assessed"] is False
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == "icoder/CodedEvidence/v11"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-evidence-extractor.v1"
    )
