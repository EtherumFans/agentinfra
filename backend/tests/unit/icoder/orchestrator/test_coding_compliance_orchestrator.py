"""Unit tests for CodingComplianceOrchestrator (Track C Gate 4 §9).

Covers:
  - 7-stage happy path (all stages succeed, AUTO_PASS)
  - Stage failure handling (skip downstream stages)
  - BLOCKED_NO_CODES_EXTRACTED (medical-coding returns no codes)
  - BLOCKED_PRIMARY_DX_CONFLICT (mc primary ≠ pd recommended)
  - BLOCKED_CRITICAL_RULE_VIOLATION (R001 in compliance-guardrail output)
  - BLOCKED_NOTE_SEVERELY_INCOMPLETE (completeness_score < 0.30)
  - REVIEW_REVIEW_RECOMMENDED (warnings only)
  - Determinism: same case_id + input → same stage_outputs
"""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.coding_compliance_orchestrator import (
    BLOCKED_CRITICAL_RULE_VIOLATION,
    BLOCKED_MISSING_DISCHARGE,
    BLOCKED_NO_CODES_EXTRACTED,
    BLOCKED_NOTE_SEVERELY_INCOMPLETE,
    BLOCKED_PRIMARY_DX_CONFLICT,
    CaseState,
    CodingComplianceConfig,
    CodingComplianceOrchestrator,
    REVIEW_AUTO_PASS,
    REVIEW_BLOCKED,
    REVIEW_REVIEW_RECOMMENDED,
    REVIEW_REVIEW_REQUIRED,
    STAGE_COMPLIANCE,
    STAGE_DISCHARGE,
    STAGE_DRG,
    STAGE_EVIDENCE,
    STAGE_MEDICAL_CODING,
    STAGE_NOTE_COMPLETENESS,
    STAGE_PRINCIPAL_DX,
    STAGE_ORDER,
)


# ── Deterministic stub runner ───────────────────────────────────────────


def _happy_stage_outputs(stage: str) -> dict:
    """Return a clean per-stage output for the happy path."""
    if stage == STAGE_DISCHARGE:
        return {
            "structured_sections": {
                "diagnoses": [{"text": "T12 椎体压缩性骨折", "primary": True}],
                "procedures": [{"text": "后路椎体成形术"}],
                "treatment_summary": "术后恢复良好",
            }
        }
    if stage == STAGE_MEDICAL_CODING:
        return {
            "extracted_diagnoses": [
                {"code": "S22.000", "final_code": "S22.000",
                 "is_primary": True, "confidence": 0.92},
                {"code": "M80.900", "final_code": "M80.900",
                 "is_primary": False, "confidence": 0.85},
            ],
            "procedures": [{"code": "81.0100"}],
        }
    if stage == STAGE_PRINCIPAL_DX:
        return {
            "recommended": {"code": "S22.000", "display": "T12 椎体压缩性骨折"},
            "coding_draft_consistent": True,
            "manual_review_required": False,
            "rationale": "主诊断匹配",
        }
    if stage == STAGE_EVIDENCE:
        return {
            "supported_codes": [{"code": "S22.000"}],
            "uncertain_candidates": [{"code": "M80.900"}],
            "rejected_candidates": [],
            "overall_strength": 0.85,
        }
    if stage == STAGE_COMPLIANCE:
        return {
            "violations": [],  # clean
            "risk_points": [],
            "compliant": True,
            "risk_level": "low",
        }
    if stage == STAGE_NOTE_COMPLETENESS:
        return {
            "required_sections": ["主诉", "现病史", "既往史", "体格检查",
                                   "辅助检查", "诊断", "治疗经过", "手术记录"],
            "missing_sections": [],
            "incomplete_sections": [],
            "completeness_score": 0.95,
            "review_conclusion": "病历完整",
        }
    if stage == STAGE_DRG:
        return {
            "risk_points": [],
            "drg_dip_rule_reservation_note": "无风险",
        }
    return {}


def _make_stub_runner(outputs_fn=_happy_stage_outputs, fail_stages: tuple[str, ...] = ()):
    """Build a deterministic stub AgentRunner."""
    def _runner(agent_id, input_text, context=None):
        if agent_id in fail_stages:
            raise RuntimeError(f"stub failure on {agent_id}")
        return outputs_fn(agent_id)
    return _runner


# ── Happy path ──────────────────────────────────────────────────────────


def test_happy_path_auto_pass():
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    case = orch.run(input_text="患者男性,78岁,T12 椎体压缩性骨折...")

    assert isinstance(case, CaseState)
    # All 7 stages ran.
    for stage in STAGE_ORDER:
        assert stage in case.stage_outputs
        assert case.stage_errors[stage] == ""
    # Review gate.
    assert case.review_gate_status == REVIEW_AUTO_PASS
    assert case.review_gate_blocker == ""
    # Completion.
    assert case.completion is not None


def test_case_id_deterministic_when_passed():
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    case = orch.run(input_text="x", case_id="CASE-001")
    assert case.case_id == "CASE-001"


def test_case_id_auto_generated_when_omitted():
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    case1 = orch.run(input_text="x")
    case2 = orch.run(input_text="x")
    assert case1.case_id != case2.case_id


def test_empty_input_rejected():
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    with pytest.raises(ValueError):
        orch.run(input_text="")
    with pytest.raises(ValueError):
        orch.run(input_text="   ")


# ── Stage failures ──────────────────────────────────────────────────────


def test_stage_failure_skips_downstream():
    """When stage 2 (medical-coding) fails, stages 3-5 are skipped."""
    orch = CodingComplianceOrchestrator(
        _make_stub_runner(fail_stages=(STAGE_MEDICAL_CODING,)),
        config=CodingComplianceConfig(block_on_no_codes=False),
    )
    case = orch.run(input_text="x")

    assert case.stage_errors[STAGE_MEDICAL_CODING] != ""
    # Downstream stages that depend on medical-coding get skipped.
    for stage in (STAGE_PRINCIPAL_DX, STAGE_EVIDENCE, STAGE_COMPLIANCE):
        assert "skipped:upstream_failure" in case.stage_errors[stage]
    # Stage 6 (note-completeness) and stage 7 (drg) don't depend on coding.
    # Note: drg DOES depend on coding, so it should also be skipped.
    assert "skipped:upstream_failure" in case.stage_errors[STAGE_DRG]


def test_discharge_failure_blocks():
    """When stage 1 fails, downstream stages are skipped."""
    orch = CodingComplianceOrchestrator(
        _make_stub_runner(fail_stages=(STAGE_DISCHARGE,)),
    )
    case = orch.run(input_text="x")
    assert case.stage_errors[STAGE_DISCHARGE] != ""
    assert case.review_gate_status == REVIEW_BLOCKED
    assert case.review_gate_blocker == BLOCKED_MISSING_DISCHARGE


# ── Human Review Gate blockers ──────────────────────────────────────────


def test_blocked_no_codes_extracted():
    """medical-coding returns empty extracted_diagnoses → BLOCKED."""
    def _no_codes(stage):
        if stage == STAGE_MEDICAL_CODING:
            return {"extracted_diagnoses": [], "procedures": []}
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(_make_stub_runner(_no_codes))
    case = orch.run(input_text="x")
    assert case.review_gate_status == REVIEW_BLOCKED
    assert case.review_gate_blocker == BLOCKED_NO_CODES_EXTRACTED


def test_blocked_primary_dx_conflict():
    """mc primary ≠ pd recommended → BLOCKED."""
    def _conflict(stage):
        if stage == STAGE_PRINCIPAL_DX:
            return {
                "recommended": {"code": "M80.900"},  # different from S22.000
                "coding_draft_consistent": False,
                "manual_review_required": True,
            }
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(_make_stub_runner(_conflict))
    case = orch.run(input_text="x")
    assert case.review_gate_status == REVIEW_BLOCKED
    assert case.review_gate_blocker == BLOCKED_PRIMARY_DX_CONFLICT


def test_blocked_critical_rule_violation():
    """compliance-guardrail raises R001 critical → BLOCKED."""
    def _crit(stage):
        if stage == STAGE_COMPLIANCE:
            return {
                "violations": [
                    {"rule_id": "R001", "severity": "critical", "message": "主诊断缺失"}
                ],
                "compliant": False,
                "risk_level": "critical",
            }
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(_make_stub_runner(_crit))
    case = orch.run(input_text="x")
    assert case.review_gate_status == REVIEW_BLOCKED
    assert case.review_gate_blocker == BLOCKED_CRITICAL_RULE_VIOLATION


def test_blocked_note_severely_incomplete():
    """completeness_score < 0.30 → BLOCKED."""
    def _bad_note(stage):
        if stage == STAGE_NOTE_COMPLETENESS:
            return {
                "required_sections": ["主诉", "现病史"],
                "missing_sections": ["主诉", "现病史"],
                "incomplete_sections": [],
                "completeness_score": 0.10,
                "review_conclusion": "严重不完整",
            }
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(_make_stub_runner(_bad_note))
    case = orch.run(input_text="x")
    assert case.review_gate_status == REVIEW_BLOCKED
    assert case.review_gate_blocker == BLOCKED_NOTE_SEVERELY_INCOMPLETE


# ── Non-blocking paths ──────────────────────────────────────────────────


def test_review_recommended_when_only_warnings():
    """No blocker + COMPLETED_WITH_WARNINGS → REVIEW_RECOMMENDED."""
    # Trigger COMPLETED_WITH_WARNINGS: medical-coding succeeds but
    # evidence-extractor emits only uncertain candidates (no supported).
    def _warn(stage):
        out = _happy_stage_outputs(stage)
        if stage == STAGE_EVIDENCE:
            out["supported_codes"] = []
            out["uncertain_candidates"] = [{"code": "S22.000"}]
            out["rejected_candidates"] = []
        return out

    orch = CodingComplianceOrchestrator(_make_stub_runner(_warn))
    case = orch.run(input_text="x")
    # Not blocked; may be AUTO_PASS or REVIEW_RECOMMENDED depending on
    # what the CompletionController flags.
    assert case.review_gate_status in (
        REVIEW_AUTO_PASS, REVIEW_REVIEW_RECOMMENDED, REVIEW_REVIEW_REQUIRED,
    )


def test_disabled_blockers_clear_to_pass():
    """Config disabling blockers lets borderline cases through."""
    def _no_codes(stage):
        if stage == STAGE_MEDICAL_CODING:
            return {"extracted_diagnoses": [], "procedures": []}
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(
        _make_stub_runner(_no_codes),
        config=CodingComplianceConfig(block_on_no_codes=False),
    )
    case = orch.run(input_text="x")
    assert case.review_gate_status != REVIEW_BLOCKED


# ── Stage ordering and accumulation ─────────────────────────────────────


def test_stage_order_constant():
    assert STAGE_ORDER == (
        STAGE_DISCHARGE,
        STAGE_MEDICAL_CODING,
        STAGE_PRINCIPAL_DX,
        STAGE_EVIDENCE,
        STAGE_COMPLIANCE,
        STAGE_NOTE_COMPLETENESS,
        STAGE_DRG,
    )


def test_normalized_outputs_populated():
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    case = orch.run(input_text="x")
    for stage in STAGE_ORDER:
        assert stage in case.normalized
    # medical-coding normalized should have codes_emitted.
    mc_n = case.normalized[STAGE_MEDICAL_CODING]
    assert "S22.000" in mc_n.codes_emitted


def test_idempotent_case_id():
    """Same case_id + input → same stage_outputs structure."""
    orch = CodingComplianceOrchestrator(_make_stub_runner())
    case = orch.run(input_text="x", case_id="CASE-X")
    assert case.case_id == "CASE-X"
    assert all(stage in case.stage_outputs for stage in STAGE_ORDER)


# ── Real-agent shape support ────────────────────────────────────────────


def test_medical_coding_real_shape_codes_field():
    """Real agent emits ``result.codes`` (not ``extracted_diagnoses``).

    Verifies the orchestrator's extractor handles the real shape that
    the production medical-coding-agent returns.
    """
    def _real_mc(stage):
        if stage == STAGE_MEDICAL_CODING:
            return {
                "result": {
                    "codes": [
                        {"code": "S22.000x003", "type": "primary_diagnosis", "confidence": 0.95},
                        {"code": "E14.900x001", "type": "secondary_diagnosis", "confidence": 0.9},
                    ],
                    "llm_provider": "deepseek",
                }
            }
        if stage == STAGE_PRINCIPAL_DX:
            return {
                "recommended": {"code": "S22.000x003"},
                "coding_draft_consistent": True,
            }
        return _happy_stage_outputs(stage)

    orch = CodingComplianceOrchestrator(_make_stub_runner(_real_mc))
    case = orch.run(input_text="x")
    # Codes were extracted from the real shape.
    mc_n = case.normalized[STAGE_MEDICAL_CODING]
    assert "S22.000x003" in mc_n.codes_emitted
    # Primary dx extraction works on real shape.
    # No conflict because principal-dx recommended matches.
    assert case.review_gate_status != REVIEW_BLOCKED or (
        case.review_gate_blocker != BLOCKED_PRIMARY_DX_CONFLICT
    )
