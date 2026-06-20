"""M3 E2E Product Validation — 负向边界测试.

链路 10 + 11 + 12 联合验证:
- mode=model_evaluation 必须 501 (B0 未接)
- DRG/DIP 不可用时不伪造结果
- production_writeback_blocked 永远为 true
- report 无 F1 / accuracy 等模型效果承诺
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ── 链路 10: B0 prediction 未配置边界 ──────────────────────


def test_model_evaluation_returns_501(client):
    """链路 10: mode=model_evaluation → 501 Not Implemented."""
    r = client.post("/api/icoder/coding-review/run", json={"mode": "model_evaluation"})
    assert r.status_code == 501, f"expected 501, got {r.status_code}"
    body = r.json()
    assert "model_evaluation" in body["detail"]
    assert "M3-0" in body["detail"] or "M3" in body["detail"]


def test_model_evaluation_does_not_fabricate_prediction(client):
    """链路 10 补充: model_evaluation 即使填了 codes, 也不返回主诊断 (不伪造)."""
    r = client.post("/api/icoder/coding-review/run", json={
        "mode": "model_evaluation",
        "primary_disease_codes": "I20.000",
    })
    # 仍是 501
    assert r.status_code == 501


def test_run_does_not_output_f1_or_accuracy(client):
    """链路 10 硬性: run 响应不能含 F1 / accuracy / precision / recall."""
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "冠心病", "primary_disease_codes": "I20.000",
    })
    body = r.json()
    body_str = str(body).lower()
    assert "f1_score" not in body_str
    assert "accuracy" not in body_str
    assert "precision" not in body_str
    assert "recall" not in body_str


def test_report_does_not_output_f1_or_accuracy(client):
    """链路 8 硬性: report 不能含 F1 / accuracy 等模型效果."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]

    # HTML report
    rep_html = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep_html.text.lower()
    # disclaimer 出现即可, 但不能作为 "模型 F1=0.85" 这种具体数字
    assert "f1 = " not in html
    assert "accuracy = " not in html
    assert "precision = " not in html
    assert "recall = " not in html

    # JSON report
    rep_json = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    json_text = rep_json.text.lower()
    assert "f1_score" not in json_text
    assert "accuracy_score" not in json_text


# ── 链路 11: DRG/DIP Grouper stub 边界 ─────────────────────


def test_drg_dip_stub_returns_unavailable(client):
    """链路 11: 未配置真实分组器时, run 响应不伪造 group_code.

    M3-0 阶段 run 不返回 DRG/DIP 字段 (后续 M2b-2 接入后会单独端点).
    验证: 响应中无 group_code / payment_estimate / settlement_allowed 字段.
    """
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
        "primary_surgery_codes": "36.0600",
    })
    body = r.json()
    body_str = str(body).lower()
    assert "group_code" not in body_str
    assert "payment_estimate" not in body_str
    assert "settlement_allowed" not in body_str
    assert "医保上传" not in str(body)


def test_drg_dip_stub_manual_review_required(client):
    """链路 11 补充: manual_review_required 必须为 true (人工兜底)."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    body = r.json()
    # M3-0 阶段: 主诊断命中 → manual_review_required=true (高风险路径)
    assert body["manual_review_required"] is True


# ── 链路 12: production writeback 硬阻断 ────────────────────


def test_production_writeback_blocked_in_response(client):
    """链路 12.1: human-review response.production_writeback_blocked=true."""
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",
    })
    run_id = rr.json()["run_id"]

    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept",
        "target_code": "I66.901",
        "target_role": "primary_disease",
        "reason_code": "R007",
        "reviewer": "dr.li",
        "reviewer_role": "medical_insurance_reviewer",
    })
    body = h.json()
    assert body["production_writeback_blocked"] is True


def test_production_writeback_blocked_in_audit_log(client):
    """链路 12.2: audit_log_entry.production_writeback_blocked=true."""
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",
    })
    run_id = rr.json()["run_id"]

    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "modify",
        "target_code": "I66.901",
        "target_role": "primary_disease",
        "new_code": "I63.900",
        "reason_code": "R001",
        "reviewer": "dr.li",
    })
    body = h.json()
    assert body["audit_log_entry"]["production_writeback_blocked"] is True


def test_production_writeback_blocked_for_all_actions(client):
    """链路 12.3: 5 个 action 全部 production_writeback_blocked=true."""
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",
        "other_disease_codes": "I10.x00",
    })
    run_id = rr.json()["run_id"]

    actions = [
        ("accept", "I10.x00", "other_disease", None),
        ("reject", "I10.x00", "other_disease", None),
        ("modify", "I10.x00", "other_disease", "I10.x01"),
        ("insufficient_evidence", "I10.x00", "other_disease", None),
        ("escalate", "I10.x00", "other_disease", None),
    ]
    for action, target_code, target_role, new_code in actions:
        payload = {
            "action": action,
            "target_code": target_code,
            "target_role": target_role,
            "reason_code": "R007",
            "reviewer": "dr.li",
            "reviewer_role": "medical_insurance_reviewer",
        }
        if new_code:
            payload["new_code"] = new_code
        h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json=payload)
        body = h.json()
        if body["accepted"]:
            assert body["production_writeback_blocked"] is True, \
                f"action={action} production_writeback_blocked must be true"


def test_report_does_not_claim_production_writeback_success(client):
    """链路 12.4: report 不能含 "已写回生产" / "医保上传成功" 字样."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    # 这些字样必须 0 出现
    assert "已写回生产" not in html
    assert "已写入 EMR" not in html
    assert "已写入 HIS" not in html
    assert "医保上传成功" not in html
    assert "自动放行" not in html


def test_unavailable_run_blocks_fabrication(client):
    """链路 10+11 联合: 完全无输入 → unavailable, 不伪造诊断."""
    r = client.post("/api/icoder/coding-review/run", json={})
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["degraded"] is True
    assert body["business_result_generated"] is False
    assert body["manual_review_required"] is True
    # 主诊断不应伪造
    assert body.get("primary_diagnosis") in (None, {})
    # 高风险不应伪造
    assert body.get("high_risk_coding_points", []) == []