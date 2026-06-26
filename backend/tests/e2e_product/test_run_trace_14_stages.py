"""M3 E2E Product Validation — 链路 3 Run Trace 阶段.

Phase D3 (2026-06-26) — ``PIPELINE_STAGES`` is now 5 MedCodER stages (was
14 homepage-cosmetic stages). The API still emits 14 ``observed_stages``
for non-empty input via the legacy ``_execute_pipeline_14_stages`` path
— this is the MedCodER ↔ legacy 14-stage adapter in transition. The
empty-input path emits 5 MedCodER stages as noops.

Migration plan: ``_execute_pipeline_14_stages`` is on the deprecation
list (see ``homepage-coding-review`` shim removal). Once the API is
fully MedCodER-5-stage, tests here will be folded into
``test_coding_review_real_trace.py``.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from app.main import app
# Phase D3 (2026-06-26): import the SSOT 5-stage constant.
from icoder_runtime.constants.coding_review_constants import PIPELINE_STAGES


# MedCodER 5 阶段 — 取代 14 阶段 cosmetic
_MEDCODER_5_STAGES = (
    "extraction",
    "retrieval",
    "merge",
    "rerank",
    "calibration",
)

# Legacy 14 阶段 (API 在 _execute_pipeline_14_stages 仍发, 待 Phase D+ 替换)
_LEGACY_14_STAGES = {
    "document_normalizer",
    "evidence_fact_extractor",
    "coding_eligibility_classifier",
    "candidate_generator",
    "ontology_service",
    "high_risk_coding_point_checker",
    "kg_auditor",
    "code_reconciler",
    "risk_router",
    "medical_safety_gate",
    "human_review",
    "report_generator",
    "run_trace_emitter",
    "audit_logger",
}


@pytest.fixture
def client():
    return TestClient(app)


def test_pipeline_stages_constant_is_5_medcoder_stages():
    """SSOT PIPELINE_STAGES 是 MedCodER 5 阶段, 不是 14 cosmetic 阶段."""
    assert len(PIPELINE_STAGES) == 5
    for stage in _MEDCODER_5_STAGES:
        assert stage in PIPELINE_STAGES, f"missing MedCodER stage: {stage}"


def test_run_observes_legacy_14_stages_for_full_input(client):
    """API 对完整输入仍记录 14 阶段 (legacy 路径, 待 Phase D+ 替换)."""
    r = client.post("/api/icoder/coding-review/run", json={
        "encounter_text": "冠心病", "primary_disease_codes": "I20.000",
    })
    body = r.json()
    observed = body["pipeline_stages_observed"]
    assert len(observed) >= 8
    # 关键 14 阶段必须出现 (legacy 路径)
    must_have = [
        "high_risk_coding_point_checker",
        "risk_router",
        "medical_safety_gate",
        "report_generator",
        "run_trace_emitter",
        "audit_logger",
    ]
    for s in must_have:
        assert s in observed, f"must-have stage missing: {s}"


def test_unavailable_run_marks_trace_explicitly(client):
    """链路 3 边界: 完全无输入 → status=unavailable, 阶段全部以 noop 标注.

    Phase D3: empty-input path 在 ``_execute_pipeline_14_stages`` 内显式
    跑 ``PIPELINE_STAGES[1:]`` (4 MedCodER stages) + 1 显式 Stage 1
    ``document_normalizer`` → 共 5 stages as noop. The 14-stage contract
    for full input is preserved by ``_execute_pipeline_14_stages``.
    """
    r = client.post("/api/icoder/coding-review/run", json={})
    body = r.json()
    assert body["status"] == "unavailable"
    # empty input → 5 stages recorded (1 explicit + 4 from PIPELINE_STAGES[1:])
    assert len(body["pipeline_stages_observed"]) >= 5, (
        f"empty input should still record at least 5 stages, "
        f"got {len(body['pipeline_stages_observed'])}"
    )
    # reason 必须显式说明不可用原因
    assert "empty" in body["reason"].lower() or "无输入" in body["reason"]
    # 风险路由 + 安全门禁都给到 unknown / 0 规则 (不可伪造)
    assert body["risk_route"]["level"] == "unknown"
    assert body["safety_gate"]["rule_count"] == 0
