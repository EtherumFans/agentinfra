from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient


def test_governed_evidence_ranker_a2a_returns_same_local_contract() -> None:
    from app.main import app

    input_payload = {
        "candidate_code": "I21.0",
        "evidence_items": [{
            "evidence_id": "A", "source": "入院记录", "content": "I21.0 记录片段"
        }],
    }
    payload = {
        "jsonrpc": "2.0",
        "id": "evidence-ranker-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": json.dumps(input_payload, ensure_ascii=False)}],
                "metadata": {},
            }
        },
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/evidence-ranker/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["ranking_status"] == "RANKED"
    assert data["ranking_basis"] == "DOCUMENTATION_GROUNDING_ONLY"
    assert data["ranked_evidence"][0]["evidence_id"] == "A"
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == "icoder/EvidenceRankerOutput/v4"
    assert "backend_provider" not in data_part["metadata"]
    assert result["metadata"]["backend_provider"] == "icoder.governed-evidence-ranker.v1"
