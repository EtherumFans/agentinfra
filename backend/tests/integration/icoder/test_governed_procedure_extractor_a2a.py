from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_governed_procedure_extractor_a2a_returns_local_catalog_contract() -> None:
    from app.main import app

    text = (
        "患者男性,78岁,因 T12 椎体压缩性骨折行 T12 椎体切开复位内固定术,"
        "手术顺利,术后恢复良好。"
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "procedure-extractor-a2a",
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
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/procedure-extractor/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["procedures"][0]["code"] == "03.5304"
    assert data["procedures"][0]["display"] == "胸椎骨折切开复位内固定术"
    assert data["procedures"][0]["status"] == "performed"
    assert data["procedures"][0]["evidence_text"] in text
    assert data["non_billable_mentions"] == []
    assert data["manual_review_required"] is True
    assert data_part["metadata"]["schema_ref"] == "icoder/ProcedureCodingOutput/v8"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-procedure-extractor.v1"
    )


def test_governed_procedure_extractor_a2a_keeps_cancelled_mention_nonbillable() -> None:
    from app.main import app

    text = (
        "病程记录：原拟行腹腔镜胆囊切除术，因患者拒绝已取消，"
        "本次住院未实施任何手术或操作。"
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "procedure-extractor-cancelled-a2a",
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
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/procedure-extractor/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["procedures"] == []
    assert data["non_billable_mentions"][0]["status"] == "cancelled"
    assert data["issues_found"]
