from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_governed_navigator_a2a_returns_same_local_contract() -> None:
    from app.main import app

    payload = {
        "jsonrpc": "2.0",
        "id": "navigator-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": "诊断表述：慢性肾脏病3期。"}],
                "metadata": {},
            },
        },
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/icd10-navigator/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["search_status"] == "CANDIDATES_FOUND"
    assert data["candidate_codes"][0]["code"] == "N18.803"
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == (
        "icoder/Icd10NavigatorOutput/v4"
    )
    assert "backend_provider" not in data_part["metadata"]
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-icd-navigator.v1"
    )
