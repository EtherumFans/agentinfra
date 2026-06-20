"""M2a Task 3 — Medical Safety Gate calculator tests.

Verifies:
- test_medical_safety_gate_passes_with_good_metrics
- test_medical_safety_gate_blocks_primary_dx_damage
- test_medical_safety_gate_blocks_ungrounded_evidence
- test_medical_safety_gate_hard_block_on_damage
"""

from __future__ import annotations

import pytest

from icoder_runtime.m2a.safety_gate import (
    MedicalSafetyGate,
    MEDICAL_SAFETY_METRICS,
    RELEASE_GATE_RULES,
)


def test_medical_safety_gate_passes_with_good_metrics():
    """所有指标在阈值内 → pass。"""
    gate = MedicalSafetyGate()
    good = {
        "primary_dx_damage_rate": 0.0,
        "primary_dx_auto_replace_rate": 0.0,
        "other_dx_overcode_rate": 0.02,
        "other_dx_miss_rate": 0.05,
        "procedure_net_fix_rate": 0.90,
        "evidence_grounding_rate": 0.98,
        "unsupported_code_rate": 0.01,
        "high_risk_coding_point_regression": 0.98,
        "payment_risk_misjudge_rate": 0.02,
        "human_review_consistency_rate": 0.92,
        "rule_conflict_unresolved_rate": 0.0,
        "auto_passed_no_evidence_count": 0,
    }
    r = gate.evaluate(metrics=good)
    assert r.status == "pass"
    assert r.release_blocked is False
    assert r.insurance_upload_blocked is False
    assert r.human_required is False
    assert r.blocked_metrics == []


def test_medical_safety_gate_blocks_primary_dx_damage():
    """primary_dx_damage_rate > 0 → block release（REL-001）。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(metrics={"primary_dx_damage_rate": 0.01})
    assert r.status == "block"
    assert r.release_blocked is True
    assert "REL-001" in r.triggered_rules
    assert "primary_dx_damage_rate" in r.blocked_metrics


def test_medical_safety_gate_blocks_ungrounded_evidence():
    """evidence_grounding_rate < 0.95 → block release（REL-003）。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(metrics={"evidence_grounding_rate": 0.80})
    assert r.status == "block"
    assert r.release_blocked is True
    assert "REL-003" in r.triggered_rules
    assert "evidence_grounding_rate" in r.blocked_metrics


def test_medical_safety_gate_hard_block_on_damage():
    """REL-001 触发即硬阻断，warning 也不能 override。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(
        metrics={"primary_dx_damage_rate": 0.005, "evidence_grounding_rate": 0.99}
    )
    assert r.status == "block"
    assert r.release_blocked is True
    assert r.insurance_upload_blocked is False  # 仅 release 被 block
    # 同时多个规则可触发
    assert "REL-001" in r.triggered_rules


def test_medical_safety_gate_primary_dx_replace_ungrounded():
    """主诊断替换 + 证据未回链 → block_auto_writeback（REL-008，threshold-free）。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(
        metrics={},
        primary_dx_change_attempted=True,
        evidence_grounded=False,
    )
    assert r.primary_dx_change_blocked is True
    assert r.release_blocked is True
    assert r.human_required is True
    assert "REL-008" in r.triggered_rules


def test_medical_safety_gate_payment_misjudge_blocks_upload():
    """payment_risk_misjudge_rate > 0.05 → 阻断医保上传（REL-006）。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(metrics={"payment_risk_misjudge_rate": 0.10})
    assert r.insurance_upload_blocked is True
    assert "REL-006" in r.triggered_rules
    # release 仍可通过（仅 payment 阻断）
    assert r.release_blocked is False


def test_medical_safety_gate_auto_passed_no_evidence_requires_human():
    """auto_passed_no_evidence_count > 0 → 强制人工 + 阻断发布（REL-007）。"""
    gate = MedicalSafetyGate()
    r = gate.evaluate(metrics={"auto_passed_no_evidence_count": 1})
    assert r.release_blocked is True
    assert r.human_required is True
    assert "REL-007" in r.triggered_rules


def test_medical_safety_gate_12_metrics_8_rules_consistent():
    """12 指标 + 8 规则存在性校验（防止 silent drop）。"""
    assert len(MEDICAL_SAFETY_METRICS) == 12
    assert len(RELEASE_GATE_RULES) == 8
    rule_ids = [r["rule_id"] for r in RELEASE_GATE_RULES]
    for rid in ("REL-001", "REL-002", "REL-003", "REL-004", "REL-005", "REL-006", "REL-007", "REL-008"):
        assert rid in rule_ids, f"Missing release gate rule {rid}"
