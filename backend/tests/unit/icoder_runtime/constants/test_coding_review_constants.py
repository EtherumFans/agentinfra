"""iCoDer Coding Review Constants — SSOT unit tests.

Phase D3 (2026-06-26) — these tests lock down the canonical
constants that were moved out of the deprecated
``official_agents.homepage_coding_review`` shim. Any future
agent_pack update that wants to change these values must update
this test AND the corresponding Agent Card metadata.
"""

from __future__ import annotations

import pytest

from icoder_runtime.constants.coding_review_constants import (
    AGENT_CATEGORY,
    AGENT_REF,
    ALLOWED_HUMAN_ACTIONS,
    ALLOWED_HUMAN_DECISIONS,
    PIPELINE_STAGES,
    PIPELINE_VALIDATION_DISCLAIMER,
    PRIORITY_HIGH_RISK_CODES,
    __all__,
)


# ── 1. SSOT module surface ──────────────────────────────────────────────


def test_module_exports_canonical_symbols():
    """__all__ lists the 7 canonical constants — no legacy symbols leak in."""
    expected = {
        "AGENT_REF",
        "AGENT_CATEGORY",
        "PIPELINE_STAGES",
        "PRIORITY_HIGH_RISK_CODES",
        "ALLOWED_HUMAN_DECISIONS",
        "ALLOWED_HUMAN_ACTIONS",
        "PIPELINE_VALIDATION_DISCLAIMER",
    }
    assert set(__all__) == expected, (
        f"SSOT surface drifted: extra={set(__all__) - expected}, "
        f"missing={expected - set(__all__)}"
    )


# ── 2. AGENT_REF is the MedCodER agent ──────────────────────────────────


def test_agent_ref_is_medcoder_coding_review_agent():
    """AGENT_REF references the canonical MedCodER agent, not the legacy homepage."""
    assert AGENT_REF == "icoder/medcoder-coding-review-agent@1.0.0"
    # The legacy homepage-coding-review string MUST NOT appear here
    assert "homepage-coding-review" not in AGENT_REF


def test_agent_category_is_medical_coding():
    """AGENT_CATEGORY changed from 'official_reference_agent' to 'medical-coding'."""
    assert AGENT_CATEGORY == "medical-coding"


# ── 3. PIPELINE_STAGES is 5 MedCodER stages, not 14 cosmetic ───────────


def test_pipeline_stages_has_5_medcoder_stages():
    """PIPELINE_STAGES is the 5-stage MedCodER pipeline (NAACL 2025)."""
    assert len(PIPELINE_STAGES) == 5
    assert PIPELINE_STAGES == [
        "extraction",
        "retrieval",
        "merge",
        "rerank",
        "calibration",
    ]


def test_pipeline_stages_does_not_contain_legacy_14_stage_names():
    """The 14-stage cosmetic stages are GONE from the SSOT."""
    legacy_names = {
        "document_normalizer",
        "evidence_fact_extractor",
        "coding_eligibility_classifier",
        "candidate_generator",
        "ontology_service",
        "high_risk_coding_point_checker",
        "kg_auditor",
        "code_reconciler",  # ← this is the legacy stage, NOT the expert
        "risk_router",
        "medical_safety_gate",
        "human_review",
        "report_generator",
        "run_trace_emitter",
        "audit_logger",
    }
    leak = set(PIPELINE_STAGES) & legacy_names
    assert not leak, f"legacy 14-stage names leaked into SSOT: {leak}"


# ── 4. PRIORITY_HIGH_RISK_CODES is the 5-码 set ────────────────────────


def test_priority_high_risk_codes_is_5_codes():
    """The 5 重点高风险易错编码点 are stable clinical constants."""
    assert len(PRIORITY_HIGH_RISK_CODES) == 5
    assert PRIORITY_HIGH_RISK_CODES == {
        "I66.901",      # 脑梗死
        "J98.414",      # 肺不张
        "M80.900",      # 骨质疏松
        "45.1600x001",  # 胃镜活检
        "Z51.102",      # 化疗
    }


# ── 5. Human-review enums ─────────────────────────────────────────────


def test_allowed_human_decisions_has_5_values():
    assert len(ALLOWED_HUMAN_DECISIONS) == 5
    assert ALLOWED_HUMAN_DECISIONS == {
        "support_direct", "support_indirect", "insufficient", "reject", "past_history",
    }


def test_allowed_human_actions_has_5_values():
    assert len(ALLOWED_HUMAN_ACTIONS) == 5
    assert ALLOWED_HUMAN_ACTIONS == {
        "accept", "reject", "modify", "insufficient_evidence", "escalate",
    }


def test_human_decisions_overlap_with_actions_is_only_reject():
    """decisions + actions are distinct vocabularies with only ``reject`` shared.

    ``reject`` is shared because a reviewer can both ``reject`` the AI's
    suggestion (action) AND provide a ``reject`` justification (decision).
    All other 8 values are unique to their respective vocabulary.
    """
    overlap = ALLOWED_HUMAN_DECISIONS & ALLOWED_HUMAN_ACTIONS
    assert overlap == {"reject"}, (
        f"expected only 'reject' to overlap, got {overlap}"
    )


# ── 6. Pipeline validation disclaimer wording ─────────────────────────


def test_disclaimer_mentions_medcoder():
    """The disclaimer must reference the MedCodER agent by name."""
    assert "MedCodER" in PIPELINE_VALIDATION_DISCLAIMER
    assert AGENT_REF in PIPELINE_VALIDATION_DISCLAIMER


def test_disclaimer_forbids_healthcare_uploads():
    """The disclaimer must explicitly forbid 医保 upload (硬性)."""
    assert "医保" in PIPELINE_VALIDATION_DISCLAIMER
    assert "生产写回" in PIPELINE_VALIDATION_DISCLAIMER


def test_disclaimer_does_not_claim_model_effect():
    """The disclaimer must NOT make F1/accuracy/precision claims (红线)."""
    # The English-word form is what the e2e test greps for; the SSOT uses
    # Chinese wording but the contract is the same — no model effect claimed.
    for kw in ("f1 =", "accuracy =", "precision =", "recall ="):
        assert kw not in PIPELINE_VALIDATION_DISCLAIMER.lower(), (
            f"disclaimer must not claim model effect: {kw}"
        )


def test_disclaimer_does_not_reference_legacy_agent():
    """The disclaimer must NOT reference the legacy homepage-coding-review agent."""
    assert "homepage-coding-review" not in PIPELINE_VALIDATION_DISCLAIMER
    assert "homepage_coding_review" not in PIPELINE_VALIDATION_DISCLAIMER
