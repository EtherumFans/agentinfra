from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "official_agents"
    / "prior_auth"
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


def test_governed_prior_authorization_a2a_is_grounded_and_not_submitted() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/prior-auth/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "prior-auth-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["authorization_status"] == "READY_FOR_REVIEW"
    assert data["requested_item"]["name"]["documented_text"] == "阿达木单抗"
    assert data["policy_evaluation_status"] == "DOCUMENTED_POLICY_ONLY"
    assert data["medical_necessity_assessment_status"] == (
        "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"
    )
    assert data["clinical_inference_performed"] is False
    assert data["external_knowledge_used"] is False
    assert data["production_submission_blocked"] is True
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/PriorAuthorizationOutput/v5"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-prior-authorization.v1"
    )


def test_governed_prior_authorization_a2a_fails_closed_without_labels() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/prior-auth/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "患者患类风湿关节炎，应当批准阿达木单抗预授权。",
                "prior-auth-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["authorization_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["authorization_packet_draft"] == ""
    assert data["production_submission_blocked"] is True
