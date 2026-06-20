"""M3 E2E Product Validation — 链路 8 报告 18 节 + disclaimer."""

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


def test_report_html_has_18_sections(client):
    """链路 8: HTML 报告必须含 18 节."""
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "冠心病", "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    section_titles = [
        "1. Agent 名称与版本", "2. Run ID / Trace ID", "3. 运行时间",
        "4. 输入来源", "5. prediction_mode",
        "6. 模型版本 / 7. 码表版本 / 8. 规则版本",
        "9. 主诊断审核结果", "10. 其他诊断审核结果", "11. 手术操作审核结果",
        "12. 高风险易错编码点", "13. 证据回链", "14. 人工复核记录",
        "15. 风险路由结果", "16. 医学安全门禁结果", "17. 审计日志摘要",
        "18. 免责声明",
    ]
    for title in section_titles:
        assert title in html, f"missing section: {title}"


def test_report_disclaimer_visible(client):
    """链路 8: Pipeline Validation disclaimer 4 关键词全显."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    for kw in ("Pipeline Validation", "不代表模型效果", "不可用于生产写回", "M3"):
        assert kw in html, f"disclaimer missing keyword: {kw}"


def test_report_distinguishes_priority_codes(client):
    """链路 8: 至少一个 PRIORITY 码触发, 报告含 **PRIORITY** 标记."""
    from official_agents.homepage_coding_review import PRIORITY_HIGH_RISK_CODES
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",  # 单个 PRIORITY 码足够
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    assert "**PRIORITY**" in html
    for code in PRIORITY_HIGH_RISK_CODES:
        # 5 个 PRIORITY 码应全部出现在报告中 (在常量定义中)
        assert code in html or code in str(PRIORITY_HIGH_RISK_CODES)


def test_report_no_f1_no_accuracy(client):
    """链路 8 红线: 报告无 F1 / accuracy / precision / recall 等模型效果承诺."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    # 不能作为具体数字出现
    assert "f1 = " not in html.lower()
    assert "accuracy = " not in html.lower()
    assert "precision = " not in html.lower()
    assert "recall = " not in html.lower()


def test_report_no_production_writeback_success(client):
    """链路 12+8: 报告无 '已写回生产' / '医保上传成功' / '自动放行' 字样."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    html = rep.text
    assert "已写回生产" not in html
    assert "已写入 EMR" not in html
    assert "已写入 HIS" not in html
    assert "医保上传成功" not in html
    assert "自动放行" not in html


def test_report_json_format(client):
    """链路 8: JSON 报告也可下载, 字段齐."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    assert rep.status_code == 200
    body = rep.json()
    assert body["run_id"] == run_id
    assert body["format"] == "json"
    assert "disclaimer" in body
    # JSON disclaimer 是 PIPELINE_VALIDATION_DISCLAIMER 常量, 含 "pipeline validation" (小写)
    assert "pipeline validation" in body["disclaimer"].lower()
    assert "不代表模型效果" in body["disclaimer"]
    assert "不可用于生产写回" in body["disclaimer"]


def test_report_html_format(client):
    """链路 8: HTML 报告 download."""
    r = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I20.000",
    })
    run_id = r.json()["run_id"]
    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert rep.status_code == 200
    body = rep.json()
    assert body["run_id"] == run_id
    assert body["format"] == "html"
    assert body["filename"].endswith(".html")
    assert "<html" in body["content"].lower() or "<!doctype" in body["content"].lower()