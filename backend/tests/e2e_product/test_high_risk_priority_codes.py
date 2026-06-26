"""M3 E2E Product Validation — 链路 6 高风险易错编码点 (5 PRIORITY 码).

覆盖:
- 5 PRIORITY 码全部能触发
- 触发后 human_review_required=true
- SoftSpot 字样在后端代码中不出现
- "高风险易错编码点" 术语统一
"""

from __future__ import annotations

import re
import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from app.main import app
# Phase D3 (2026-06-26): import from the SSOT — the homepage-coding-review
# shim is removed.
from icoder_runtime.constants.coding_review_constants import PRIORITY_HIGH_RISK_CODES


@pytest.fixture
def client():
    return TestClient(app)


# ── 链路 6 自动化 ─────────────────────────────────────────


def test_priority_codes_constants():
    """5 PRIORITY 码常量必须包含 5 个特定 ICD 码."""
    assert len(PRIORITY_HIGH_RISK_CODES) == 5
    expected = {"I66.901", "J98.414", "M80.900", "45.1600x001", "Z51.102"}
    assert set(PRIORITY_HIGH_RISK_CODES) == expected


@pytest.mark.parametrize("code", PRIORITY_HIGH_RISK_CODES)
def test_each_priority_code_triggers_high_risk(client, code):
    """5 PRIORITY 码各自能触发 + human_review_required=true + is_priority=true."""
    # 45.1600x001 是 surgery 码, 走 primary_surgery_codes
    if code.startswith("45") or code.startswith("Z51"):
        payload = {"primary_surgery_codes": code}
    else:
        payload = {"primary_disease_codes": code}

    r = client.post("/api/icoder/coding-review/run", json=payload)
    assert r.status_code == 200, f"{code} run failed: {r.text}"
    body = r.json()
    high_risk = body.get("high_risk_coding_points", [])
    assert any(h["code"] == code for h in high_risk), \
        f"{code} (PRIORITY) must trigger, got: {high_risk}"
    hit = next(h for h in high_risk if h["code"] == code)
    assert hit["is_priority"] is True
    assert hit["human_review_required"] is True


def test_priority_code_reject_without_reason_blocked(client):
    """5 PRIORITY 码 reject 缺 reason_code → 校验失败."""
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "I66.901",
    })
    run_id = rr.json()["run_id"]
    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "reject",
        "target_code": "I66.901",
        "target_role": "primary_disease",
        "reviewer": "dr.li",
        # no reason_code
    })
    body = h.json()
    assert body["accepted"] is False
    assert any("reason_code" in e for e in body["validation_errors"])


def test_priority_code_insufficient_without_reason_blocked(client):
    """5 PRIORITY 码 insufficient_evidence 缺 reason_code → 校验失败."""
    rr = client.post("/api/icoder/coding-review/run", json={
        "primary_disease_codes": "J98.414",
    })
    run_id = rr.json()["run_id"]
    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "insufficient_evidence",
        "target_code": "J98.414",
        "target_role": "primary_disease",
        "reviewer": "dr.li",
        # no reason_code
    })
    body = h.json()
    assert body["accepted"] is False
    assert any("reason_code" in e for e in body["validation_errors"])


# ── 术语检查 (链路 6 红线) ─────────────────────────────────


def test_no_softspot_in_official_agents():
    """红线: SoftSpot 字样不出现在 official_agents 目录."""
    official_agents_dir = REPO_ROOT / "official_agents"
    if not official_agents_dir.exists():
        pytest.skip("official_agents dir not found")
    for path in official_agents_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "SoftSpot" not in content, \
            f"SoftSpot found in {path}"


def test_no_softspot_in_app_api():
    """红线: SoftSpot 字样不出现在 app/api 目录."""
    app_api_dir = REPO_ROOT / "app" / "api"
    if not app_api_dir.exists():
        pytest.skip("app/api dir not found")
    for path in app_api_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "SoftSpot" not in content, \
            f"SoftSpot found in {path}"


def test_chinese_term_used():
    """红线: "高风险易错编码点" 术语在 SSOT 常量文件中存在.

    Phase D3 (2026-06-26): 旧 ``official_agents/homepage-coding-review/__init__.py``
    已删, 常量已迁到 ``icoder_runtime/constants/coding_review_constants.py``.
    """
    ssot_file = REPO_ROOT / "icoder_runtime" / "constants" / "coding_review_constants.py"
    if not ssot_file.exists():
        pytest.skip("coding_review_constants.py SSOT not found")
    content = ssot_file.read_text(encoding="utf-8")
    assert "高风险易错编码点" in content, \
        "官方术语 '高风险易错编码点' 必须在 SSOT 常量文件中存在"


def test_report_uses_chinese_term():
    """红线: 报告生成器使用 '高风险易错编码点' 术语."""
    report_file = REPO_ROOT / "icoder_runtime" / "reports" / "coding_review_report.py"
    if not report_file.exists():
        pytest.skip("coding_review_report.py not found")
    content = report_file.read_text(encoding="utf-8")
    assert "高风险易错编码点" in content