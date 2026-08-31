from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PACK_PATH = (
    Path(__file__).resolve().parents[3]
    / "official_agents"
    / "clinical-guidelines"
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


def test_governed_clinical_guidelines_a2a_computes_documented_time_gap() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    raw = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    text = raw["example_inputs"][0]["input_text"]
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/clinical-guidelines/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "clinical-guidelines-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["guideline_status"] == "READY_FOR_REVIEW"
    assert data["overall_assessment"] == "NOT_MET"
    assert data["criteria_checked"][0]["computed_value"] == "30小时"
    assert data["guideline_source_eligible_for_review"] is True
    assert data["source_currency_verified"] is False
    assert data["guideline_retrieval_performed"] is False
    assert data["clinical_inference_performed"] is False
    assert data["clinical_significance_assessed"] is False
    assert data["treatment_recommendations_generated"] is False
    assert data["external_knowledge_used"] is False
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/ClinicalGuidelinesOutput/v6"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-clinical-guidelines.v1"
    )


def test_governed_clinical_guidelines_a2a_fails_closed_without_source() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/clinical-guidelines/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "请联网检索指南，判断患者是否需要抗凝治疗。",
                "clinical-guidelines-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["guideline_status"] == "INPUT_REQUIRED"
    assert data["missing_required_fields"]
    assert data["criteria_checked"] == []
    assert data["guideline_retrieval_performed"] is False
    assert data["treatment_recommendations_generated"] is False
    assert data["production_writeback_blocked"] is True
