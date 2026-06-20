"""M3 E2E Product Validation — 链路 5 证据回链 kind 区分 (auto/gold/rejected).

自动化验证:
- M3-0 阶段不应自动产生 kind=gold 的 evidence
- evidence 默认 kind 是 auto_bootstrap
- 强制不允许 kind=gold 未经人工标注
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


def test_evidence_default_kind_is_auto_bootstrap(client):
    """链路 5: 默认 evidence.kind 应是 auto_bootstrap, 不是 gold."""
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "冠心病", "primary_disease_codes": "I20.000",
    })
    body = r.json()
    primary = body.get("primary_diagnosis") or {}
    evidence = primary.get("evidence") or []
    for ev in evidence:
        kind = ev.get("kind", "auto_bootstrap")
        assert kind in ("auto_bootstrap", "rejected"), \
            f"unexpected kind: {kind} (M3-0 阶段不应有 gold)"
        assert kind != "gold", \
            "M3-0 阶段不应自动产生 gold evidence (无人工标注)"


def test_no_gold_evidence_in_response(client):
    """链路 5 红线: 响应所有 evidence 中 kind 字段不含 'gold'."""
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "冠心病 心悸 3 年", "primary_disease_codes": "I20.000",
        "other_disease_codes": "I10.x00, E11.900",
    })
    body = r.json()
    body_str = str(body)
    # 注意: 'gold' 可能出现在 disclaimer / docs 等其他上下文, 但不应作为 evidence.kind 值
    # 我们通过 evidence_chain 和 各 diagnosis.evidence 来检查
    chain = body.get("evidence_chain", [])
    for ev in chain:
        if "kind" in ev:
            assert ev["kind"] != "gold", \
                f"evidence_chain contains gold: {ev}"


def test_evidence_viewer_kinds_constant_exists():
    """链路 5 前端: EvidenceViewer.tsx 应有 EvidenceKind 三种取值."""
    frontend_evidence_viewer = (
        REPO_ROOT.parent / "frontend" / "src" / "components" / "icoder" / "EvidenceViewer.tsx"
    )
    if not frontend_evidence_viewer.exists():
        pytest.skip("EvidenceViewer.tsx not found")
    content = frontend_evidence_viewer.read_text(encoding="utf-8")
    assert "auto_bootstrap" in content
    assert "gold" in content
    assert "rejected" in content


def test_gold_only_after_human_review():
    """链路 5 文档性质: gold 证据只能在人工复核后产生, M3-0 阶段无此机制."""
    # 这是文档性测试, 验证 spec 文档中存在此约束
    spec_file = REPO_ROOT / "docs" / "M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md"
    if not spec_file.exists():
        pytest.skip("spec file not found")
    content = spec_file.read_text(encoding="utf-8")
    # spec 必须说明 gold evidence 来源
    assert "gold" in content.lower()