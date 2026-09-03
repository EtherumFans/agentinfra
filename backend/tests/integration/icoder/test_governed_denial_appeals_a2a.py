from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "official_agents"
    / "denial-appeals"
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


def test_governed_denial_appeals_a2a_is_grounded_and_not_submitted() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/denial-appeals/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "denial-appeals-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["appeal_status"] == "READY_FOR_REVIEW"
    assert data["denial_snapshot"]["claim_id"]["documented_text"] == "TEST-CLAIM-001"
    assert data["policy_evaluation_status"] == "DOCUMENTED_POLICY_ONLY"
    assert data["denial_classification_status"] == "DOCUMENTED_ONLY_NO_INFERENCE"
    assert data["denial_root_cause_inferred"] is False
    assert data["medical_coding_validation_performed"] is False
    assert data["external_knowledge_used"] is False
    assert data["production_submission_blocked"] is True
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["evidence_text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/DenialAppealOutput/v3"
    assert result["metadata"]["backend_provider"] == "icoder.governed-denial-appeals.v1"


def test_governed_denial_appeals_a2a_fails_closed_without_labels() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/denial-appeals/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "发生拒付，请自动推断根因并立即提交申诉。",
                "denial-appeals-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["appeal_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["appeal_letter_draft"] == ""
    assert data["production_submission_blocked"] is True
