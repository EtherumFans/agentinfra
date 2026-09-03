from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "official_agents"
    / "principal_diagnosis_review"
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


def test_governed_principal_diagnosis_review_a2a_is_grounded_not_selected() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/principal-diagnosis-review/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "principal-diagnosis-review-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["review_status"] == "READY_FOR_CODER_REVIEW"
    assert data["documented_coding_draft"]["code"] == "S22.000"
    assert data["draft_in_candidate_set"] is True
    assert data["selection_basis_status"] == "DOCUMENTED"
    assert data["diagnosis_extraction_performed"] is False
    assert data["code_assignment_performed"] is False
    assert data["principal_diagnosis_selection_performed"] is False
    assert data["clinical_inference_performed"] is False
    assert data["external_rules_used"] is False
    assert data["production_submission_blocked"] is True
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/PrincipalDxReview/v11"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-principal-diagnosis-review.v1"
    )


def test_governed_principal_diagnosis_review_a2a_requires_coder_draft() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/principal-diagnosis-review/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "请从肺炎和心力衰竭中自动推荐主诊断。",
                "principal-diagnosis-review-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["review_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["candidates"] == []
    assert data["diagnosis_extraction_performed"] is False
    assert data["principal_diagnosis_selection_performed"] is False
    assert data["production_writeback_blocked"] is True
