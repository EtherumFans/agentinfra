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


def test_governed_rule_explainer_a2a_returns_catalog_only_contract() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/rule-explainer/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("请解释 ICD-10-CN 编码 I50.9。", "rule-explainer-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["status"] == "REQUIRES_REVIEW"
    assert data["catalog_status"] == "CATEGORY_OR_PREFIX"
    assert data["assignable"] is False
    assert data["hierarchy"]["children"][0]["code"] == "I50.900"
    assert data["rule_content_status"] == "UNAVAILABLE_IN_GOVERNED_ASSET"
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == "icoder/RuleExplanationOutput/v4"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-rule-explainer.v1"
    )


def test_governed_rule_explainer_a2a_fails_closed_for_unknown_code() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/rule-explainer/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("请解释 ICD-10-CN 编码 Z99.999。", "rule-unknown-a2a"),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["catalog_status"] == "NOT_FOUND"
    assert data["assignable"] is False
    assert data["manual_review_required"] is True
