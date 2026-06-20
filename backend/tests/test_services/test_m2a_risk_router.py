"""M2a Task 2 — Real 4-tier Risk Router tests.

Verifies:
- test_risk_router_classifies_4_tiers
- test_risk_router_primary_dx_change_is_critical
- test_risk_router_medium_draft_only
- test_risk_router_sample_entering_production_is_critical_reject
"""

from __future__ import annotations

import pytest

from icoder_runtime.m2a.risk_router import RiskRouter, ACTION_MATRIX


def test_risk_router_classifies_4_tiers():
    """RiskRouter 应当能输出 4 档。"""
    router = RiskRouter()

    # low
    r_low = router.route(indicators={"evidence_grounded": True})
    assert r_low.risk_level == "low"
    assert r_low.actions["auto_apply_allowed"] is True

    # medium
    r_med = router.route(indicators={"evidence_weak": True})
    assert r_med.risk_level == "medium"
    assert r_med.actions["auto_apply_allowed"] is False
    assert r_med.actions["draft_writeback_allowed"] is True
    assert r_med.actions["payment_upload_allowed"] is False

    # high
    r_high = router.route(indicators={"high_risk_coding_point_hit": True})
    assert r_high.risk_level == "high"
    assert r_high.actions["manual_review_required"] is True
    assert r_high.actions["draft_writeback_allowed"] is True
    assert r_high.actions["payment_upload_allowed"] is False

    # critical
    r_crit = router.route(indicators={"primary_dx_change_possible": True})
    assert r_crit.risk_level == "critical"
    assert r_crit.actions["block_insurance_upload"] is True
    assert r_crit.actions["auto_apply_allowed"] is False
    assert r_crit.actions["draft_writeback_allowed"] is False


def test_risk_router_primary_dx_change_is_critical():
    """主诊断可能改变必定是 critical。"""
    router = RiskRouter()
    # 即使其他指标都是 low，primary_dx_change_possible 仍应触发 critical
    r = router.route(indicators={
        "primary_dx_change_possible": True,
        "evidence_grounded": True,
    })
    assert r.risk_level == "critical"
    assert any("主诊断" in s for s in r.risk_reasons)


def test_risk_router_medium_draft_only():
    """中风险只允许 draft，不允许 auto-apply 也不允许医保上传。"""
    router = RiskRouter()
    r = router.route(indicators={"candidate_scores_close": True})
    assert r.risk_level == "medium"
    assert r.actions["auto_apply_allowed"] is False
    assert r.actions["draft_writeback_allowed"] is True
    assert r.actions["manual_review_required"] is False
    assert r.actions["payment_upload_allowed"] is False
    # can_writeback helper
    assert router.can_writeback("medium", "draft") is True
    assert router.can_writeback("medium", "auto") is False
    assert router.can_writeback("medium", "payment") is False


def test_risk_router_sample_entering_production_is_critical_reject():
    """sample 数据进入生产 trace → critical + 拒绝。"""
    router = RiskRouter()
    # case 1: is_sample=True
    r1 = router.route(indicators={}, is_sample=True, data_source="sample")
    assert r1.risk_level == "critical"
    assert r1.sample_rejected is True
    assert any("占位模拟数据" in s for s in r1.risk_reasons)
    # case 2: data_source="sample" only
    r2 = router.route(indicators={}, data_source="sample", production_allowed=False)
    assert r2.risk_level == "critical"
    assert r2.sample_rejected is True
    # case 3: production_allowed=False but data_source=real (defensive)
    r3 = router.route(indicators={}, production_allowed=False)
    assert r3.risk_level == "critical"
    assert r3.sample_rejected is True
