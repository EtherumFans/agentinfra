"""M3 E2E Product Validation — 完整 pipeline_validation 流程测试.

链路 2+3+5+6+7+8+9+12 联合验证:
1. POST /run (pipeline_validation 模式)
2. 验证 run_id / trace_id / 14 阶段
3. 验证高风险易错编码点触发
4. 验证自动证据 (auto_bootstrap)
5. 提交 human-review (5 校验规则)
6. GET /report (18 节 + disclaimer)
7. 验证 production_writeback_blocked=true (5 处)
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from app.main import app
# Phase A A3 (2026-06-25): homepage_coding_review is deprecated; pull the
# canonical constants from the inlined location in app.api.icoder_coding_review.
from app.api.icoder_coding_review import (
    AGENT_REF, AGENT_CATEGORY, PRIORITY_HIGH_RISK_CODES, PIPELINE_STAGES,
)


@pytest.fixture
def client():
    return TestClient(app)


SAMPLE_INPUT = {
    "encounter_text": "冠心病 心悸 3 年, 加重伴夜间呼吸困难 1 周",
    "case_id": "c-e2e-full-flow-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I66.901",  # 重点码
    "other_disease_codes": "I10.x00, E11.900",
}


def test_e2e_pipeline_validation_full_flow(client):
    """完整流程: run → 验证 → human-review → report → 5 处 blocked."""
    # Step 1: POST /run
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200, f"run failed: {r.text}"
    body = r.json()

    # Step 2: 验证 run_id / trace_id
    assert "run_id" in body and len(body["run_id"]) >= 16
    assert "trace_id" in body and len(body["trace_id"]) >= 16
    assert body["agent_ref"] == AGENT_REF
    assert body["agent_category"] == AGENT_CATEGORY
    assert body["prediction_mode"] == "link_validation"

    # Step 3: 验证 14 阶段 (链路 3)
    assert "pipeline_stages_observed" in body
    observed = body["pipeline_stages_observed"]
    assert len(observed) >= 8, f"observed stages too few: {observed}"
    # 至少包含: 高风险检查器 + 风险路由 + 安全门禁
    assert "high_risk_coding_point_checker" in observed
    assert "risk_router" in observed
    assert "medical_safety_gate" in observed

    # Step 4: 验证高风险易错编码点 (链路 6)
    high_risk = body.get("high_risk_coding_points", [])
    assert any(h["code"] == "I66.901" for h in high_risk), \
        f"I66.901 (PRIORITY) must trigger high risk: {high_risk}"
    i66 = next(h for h in high_risk if h["code"] == "I66.901")
    assert i66["is_priority"] is True
    assert i66["human_review_required"] is True

    # Step 5: 验证自动证据 (链路 5)
    primary = body.get("primary_diagnosis")
    assert primary is not None
    # M3-0 阶段证据默认 auto_bootstrap, 不存在 kind=gold 的伪造
    for ev in primary.get("evidence", []):
        assert ev.get("kind", "auto_bootstrap") != "gold", \
            "M3-0 阶段不应有 gold evidence (无人工标注)"

    # Step 6: 提交 human-review (链路 7)
    run_id = body["run_id"]
    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept",
        "target_code": "I66.901",
        "target_role": "other_disease",
        "reason_code": "R007",
        "reviewer": "dr.li",
        "reviewer_role": "medical_insurance_reviewer",
    })
    assert h.status_code == 200
    h_body = h.json()
    assert h_body["accepted"] is True

    # Step 7: 验证 production_writeback_blocked (链路 12, 至少 4 处)
    assert h_body["production_writeback_blocked"] is True
    assert h_body["audit_log_entry"]["production_writeback_blocked"] is True

    # Step 8: GET /report (链路 8)
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert rep.status_code == 200
    html = rep.text
    # 18 节齐
    section_titles = [
        "1. Agent 名称与版本", "9. 主诊断审核结果",
        "12. 高风险易错编码点", "18. 免责声明",
    ]
    for title in section_titles:
        assert title in html, f"missing section: {title}"
    # disclaimer 必显
    assert "Pipeline Validation" in html
    assert "不代表模型效果" in html
    assert "不可用于生产写回" in html
    # 重点码 PRIORITY
    assert "**PRIORITY**" in html
    # 无伪造模型效果 (作为具体数字)
    assert "f1 = " not in html.lower()
    assert "accuracy = " not in html.lower()
    assert "precision = " not in html.lower()
    assert "recall = " not in html.lower()

    # Step 9: GET /{run_id} 重看
    rr = client.get(f"/api/icoder/coding-review/{run_id}")
    assert rr.status_code == 200
    assert rr.json()["run_id"] == run_id


def test_e2e_5_priority_codes_all_trigger(client):
    """链路 6 扩展: 5 PRIORITY 码全部能触发."""
    for code in PRIORITY_HIGH_RISK_CODES:
        r = client.post("/api/icoder/coding-review/run", json={
            "case_id": f"c-{code}",
            "primary_disease_codes": code,
            "other_disease_codes": "",
        })
        assert r.status_code == 200, f"{code} run failed: {r.text}"
        body = r.json()
        high_risk = body.get("high_risk_coding_points", [])
        assert any(h["code"] == code for h in high_risk), \
            f"{code} (PRIORITY) must trigger, got: {high_risk}"
        hit = next(h for h in high_risk if h["code"] == code)
        assert hit["is_priority"] is True
        assert hit["human_review_required"] is True


def test_e2e_5_validation_rules(client):
    """链路 7 完整: 5 个校验规则全部命中."""
    # 先建一个 run
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I63.900",
    })
    run_id = rr.json()["run_id"]

    # 规则 1: action 非法 → 校验失败
    r1 = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "invalid_action", "reason_code": "R007", "reviewer": "dr.li",
        "target_code": "I63.900", "target_role": "primary_disease",
    })
    body1 = r1.json()
    assert body1["accepted"] is False
    assert any("action" in e for e in body1["validation_errors"])

    # 规则 2: reason_code 缺失 → 校验失败
    r2 = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept", "reviewer": "dr.li",
        "target_code": "I63.900", "target_role": "primary_disease",
    })
    body2 = r2.json()
    assert body2["accepted"] is False
    assert any("reason_code" in e for e in body2["validation_errors"])

    # 规则 3: reviewer 缺失 → 校验失败
    r3 = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept", "reason_code": "R007",
        "target_code": "I63.900", "target_role": "primary_disease",
    })
    body3 = r3.json()
    assert body3["accepted"] is False
    assert any("reviewer" in e for e in body3["validation_errors"])

    # 规则 4: primary_disease modify 缺 new_code → 校验失败
    r4 = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "modify", "reason_code": "R001", "reviewer": "dr.li",
        "target_code": "I63.900", "target_role": "primary_disease",
    })
    body4 = r4.json()
    assert body4["accepted"] is False
    assert any("new_code" in e for e in body4["validation_errors"])

    # 规则 5: 重点码 reject 缺 reason_code → 校验失败
    rr5 = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",  # 重点码
    })
    run_id_5 = rr5.json()["run_id"]
    r5 = client.post(f"/api/icoder/coding-review/{run_id_5}/human-review", json={
        "action": "reject", "reviewer": "dr.li",
        "target_code": "I66.901", "target_role": "primary_disease",
    })
    body5 = r5.json()
    assert body5["accepted"] is False
    assert any("reason_code" in e for e in body5["validation_errors"])

    # 全填 → 通过 + production_writeback_blocked=true
    r6 = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept", "reason_code": "R007", "reviewer": "dr.li",
        "target_code": "I63.900", "target_role": "primary_disease",
    })
    body6 = r6.json()
    assert body6["accepted"] is True
    assert body6["production_writeback_blocked"] is True


def test_e2e_pipeline_validation_disclaimer_everywhere(client):
    """链路 12 + 8: production_writeback_blocked 与 disclaimer 多处可见."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",
    })
    run_id = r.json()["run_id"]

    # 1. response.disclaimer 在 report response
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    # 2. disclaimer 4 关键词
    for kw in ("Pipeline Validation", "不代表模型效果", "不可用于生产写回", "M3"):
        assert kw in html, f"disclaimer missing keyword: {kw}"

    # 3. human-review 永远 production_writeback_blocked=true
    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept", "reason_code": "R007", "reviewer": "dr.li",
        "target_code": "I66.901", "target_role": "primary_disease",
    })
    body = h.json()
    assert body["production_writeback_blocked"] is True
    assert body["audit_log_entry"]["production_writeback_blocked"] is True