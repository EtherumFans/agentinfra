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
            }
        },
    }


def _packet() -> str:
    return (
        "审核目的：开发期DRG/DIP编码风险复核\n"
        "诊断编码标准：ICD-10-CN\n"
        "诊断编码版本：医院批准版2026.1\n"
        "手术编码标准：ICD-9-CM-3\n"
        "手术编码版本：医院批准版2026.1\n"
        "患者性别：M\n"
        "患者年龄：58\n"
        "主诊断编码：I21.0|急性前壁心肌梗死|病案首页|I21.0 急性前壁心肌梗死\n"
        "次诊断编码：\n"
        "I10|原发性高血压|病案首页|I10 原发性高血压\n"
        "手术操作编码：\n"
        "00.66|经皮冠状动脉介入治疗|手术记录|00.66 经皮冠状动脉介入治疗"
    )


def test_governed_drg_dip_a2a_runs_local_candidate_review() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = _packet()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/drg-analyzer/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "drg-dip-governed-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["review_status"] == "READY_FOR_CODER_REVIEW"
    assert data["development_candidate_group"]["candidate_drg"] == "EC13"
    assert data["development_candidate_group"]["result_status"] == (
        "EXPERIMENTAL_UNVERIFIED_CANDIDATE"
    )
    assert data["official_grouping_performed"] is False
    assert data["official_dip_scoring_performed"] is False
    assert data["payment_calculation_performed"] is False
    assert data["billing_authoritative"] is False
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/DRGDIPRiskReview/v8"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-drg-dip-risk-review.v1"
    )


def test_governed_drg_dip_a2a_refuses_free_text_grouping_request() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/drg-analyzer/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "请根据病历自由文本自动分配编码、DRG和支付金额。",
                "drg-dip-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["review_status"] == "INPUT_REQUIRED"
    assert data["coded_case"]["primary_diagnosis"]["code"] == ""
    assert data["local_development_rules_used"] is False
    assert data["official_grouping_performed"] is False
    assert data["payment_calculation_performed"] is False
    assert data["production_writeback_blocked"] is True
