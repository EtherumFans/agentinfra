from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = Path(__file__).resolve().parents[3] / "official_agents" / "claim-check" / "agent_pack.json"


def _payload(text: str, request_id: str) -> dict:
    return {
        "jsonrpc": "2.0", "id": request_id, "method": "message/send",
        "params": {"message": {"role": "user", "messageId": f"msg-{uuid.uuid4().hex[:8]}",
        "parts": [{"kind": "text", "text": text}], "metadata": {}}},
    }


def test_governed_claim_check_a2a_is_grounded_and_non_submitting() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/claim-check/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "claim-check-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["review_status"] == "READY_FOR_REVIEW"
    assert data["policy_evaluation_status"] == "DOCUMENTED_POLICY_ONLY"
    assert data["clinical_support_assessed"] is False
    assert data["benefit_eligibility_determined"] is False
    assert data["production_submission_blocked"] is True
    assert data["manual_review_required"] is True
    redacted = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(redacted[slice(*item["char_span"])] == item["evidence_text"] for item in data["evidence_items"])
    assert data_part["metadata"]["schema_ref"] == "icoder/ClaimCheckOutput/v4"
    assert result["metadata"]["backend_provider"] == "icoder.governed-claim-check.v1"


def test_governed_claim_check_a2a_fails_closed_without_labels() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/claim-check/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("请确认K35.80可支付并立即提交医保结算。", "claim-check-input-required"),
        )

    assert response.status_code == 200, response.text
    data = next(part["data"] for part in response.json()["result"]["parts"] if part["kind"] == "data")
    assert data["review_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["claim_review_packet"] == ""
    assert data["production_submission_blocked"] is True
