from __future__ import annotations

import json
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


def _packet(*, answers: list[dict] | None = None) -> str:
    questionnaire = {
        "start_question_id": "q1",
        "questions": [{
            "id": "q1",
            "answer_type": "boolean",
            "required": True,
            "branches": [
                {"operator": "equals", "value": True, "next": "ep_immediate"},
                {"operator": "equals", "value": False, "next": "ep_standard"},
            ],
        }],
        "endpoints": [
            {
                "id": "ep_immediate",
                "candidate_level": "IMMEDIATE",
                "red_flag_codes": ["RF_CHEST_PAIN_HYPOTENSION"],
            },
            {
                "id": "ep_standard",
                "candidate_level": "STANDARD",
                "red_flag_codes": [],
            },
        ],
    }
    if answers is None:
        answers = [{
            "question_id": "q1",
            "value": True,
            "source_document": "护士分诊记录",
            "evidence_text": "患者突发压榨性胸痛40分钟伴大汗",
        }]
    return "\n".join([
        "审核目的：开发环境分诊问卷路径复核",
        "协议标识：CN-ED-DEMO-001",
        "协议版本：2026.08-dev",
        "协议声明状态：DEVELOPMENT_FIXTURE",
        "协议来源：iCoDer 开发测试夹具（非医院批准协议）",
        "来源记录：<<<患者突发压榨性胸痛40分钟伴大汗；血压88/56mmHg。>>>",
        "问卷定义JSON：" + json.dumps(
            questionnaire, ensure_ascii=False, separators=(",", ":")
        ),
        "问卷回答JSON：" + json.dumps(
            answers, ensure_ascii=False, separators=(",", ":")
        ),
    ])


def test_governed_triage_a2a_runs_local_questionnaire_path() -> None:
    from app.main import app
    from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

    text = _packet()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/triage/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(text, "triage-governed-a2a"),
        )

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    data = data_part["data"]
    assert data["assessment_status"] == "READY_FOR_ONSITE_REVIEW"
    assert data["acuity_level"] == "DEVELOPMENT_PROTOCOL_CANDIDATE_IMMEDIATE"
    assert data["protocol_candidate"]["candidate_level"] == "IMMEDIATE"
    assert data["transcript_extraction_performed"] is False
    assert data["questionnaire_answer_inference_performed"] is False
    assert data["clinical_inference_performed"] is False
    assert data["final_acuity_assignment_performed"] is False
    assert data["production_action_blocked"] is True
    assert data["production_writeback_blocked"] is True
    assert data["manual_review_required"] is True
    redacted_text = redact_payload([{"kind": "text", "text": text}]).value[0]["text"]
    assert all(
        redacted_text[slice(*item["char_span"])] == item["text"]
        for item in data["evidence_items"]
    )
    assert data_part["metadata"]["schema_ref"] == "icoder/TriageOutput/v5"
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-triage-questionnaire.v1"
    )


def test_governed_triage_a2a_refuses_unstructured_final_level_request() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/icoder/agents/triage/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json=_payload(
                "请从这段护士患者对话自动判断最终分诊级别并立即分流。",
                "triage-input-required",
            ),
        )

    assert response.status_code == 200, response.text
    data = next(
        part["data"]
        for part in response.json()["result"]["parts"]
        if part["kind"] == "data"
    )
    assert data["assessment_status"] == "INPUT_REQUIRED"
    assert data["acuity_level"] == "NOT_ASSIGNED"
    assert data["protocol_candidate"]["reached"] is False
    assert data["transcript_extraction_performed"] is False
    assert data["final_acuity_assignment_performed"] is False
    assert data["production_action_blocked"] is True
    assert data["production_writeback_blocked"] is True
