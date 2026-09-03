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


def test_governed_medication_reconciliation_a2a_is_grounded_and_review_only() -> None:
    from app.main import app

    text = (
        "入院前：二甲双胍0.5g bid。住院中因造影暂停；胰岛素按血糖调整。"
        "拟出院医嘱仅列二甲双胍0.5g bid。"
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/med-reconciliation/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "med-reconciliation-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["reconciliation_status"] == "COMPLETED"
    assert data["home_medications"][0]["drug_name"] == "二甲双胍"
    assert data["inpatient_medications"][0]["status"] == "HELD"
    assert data["interaction_screening_status"] == (
        "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"
    )
    assert data["interaction_risks"] == []
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == (
        "icoder/MedicationReconciliationOutput/v4"
    )
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-medication-reconciliation.v1"
    )


def test_governed_medication_reconciliation_a2a_fails_closed_without_sources() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/med-reconciliation/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload("患者因房颤长期服华法林。", "med-input-required-a2a"),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["reconciliation_status"] == "INPUT_REQUIRED"
    assert data["reconciliation_summary"] == []
    assert data["manual_review_required"] is True
