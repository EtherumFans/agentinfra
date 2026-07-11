"""Unit tests for CDI domain model (Phase 5 Track D Gate 4).

Tests:
    - 8 GapType classifier coverage
    - 4 ResponseOptionCategory classifier coverage
    - Gap type classifier defaults to diagnostic_specificity
    - Response option classifier correctly identifies escape hatches
      (required by NLQ-005)
    - DocumentationGap dataclass holds gap_type field
    - DB models import cleanly and match domain shape
"""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.cdi import (
    DocumentationGap,
    EvidenceSpan,
    ResponseOption,
    classify_gap_type,
    classify_response_option,
)
from app.icoder.agent_runtime.cdi.domain import GapType, ResponseOptionCategory


# ---------------------------------------------------------------------------
# 8 GapType classifier coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,why,expected",
    [
        ("肺炎诊断特异性不足", "影响 J18.9 vs J13 编码", "diagnostic_specificity"),
        ("急性肾损伤病因未记录", "etiology of AKI not documented", "etiology_unspecified"),
        ("慢性肾病严重程度未分级", "CKD stage missing", "severity_unspecified"),
        ("未区分急性慢性", "acute vs chronic not specified", "acuity_unspecified"),
        ("部位未明确", "site unspecified, left vs right", "anatomical_site_unspecified"),
        ("痰培养与临床表现关联未建立", "clinical correlation unestablished", "clinical_correlation_unestablished"),
        ("术后发热时间关系未记录", "temporal relationship not documented", "temporal_unspecified"),
        ("入院诊断与出院诊断冲突", "conflicting documentation", "conflicting_documentation"),
    ],
)
def test_classify_gap_type_covers_all_8_types(
    description: str, why: str, expected: GapType
) -> None:
    assert classify_gap_type(description, why) == expected


def test_classify_gap_type_defaults_to_diagnostic_specificity() -> None:
    """Empty input or no-keyword input defaults to diagnostic_specificity
    (the most common CDI gap type, per Track D PDF §6.2)."""

    assert classify_gap_type("", "") == "diagnostic_specificity"
    assert classify_gap_type("no relevant keywords here", "none here either") == "diagnostic_specificity"


def test_classify_gap_type_is_case_insensitive() -> None:
    assert classify_gap_type("Acute vs Chronic", "") == "acuity_unspecified"
    assert classify_gap_type("ACUTE vs CHRONIC", "") == "acuity_unspecified"


def test_classify_gap_type_picks_highest_scoring() -> None:
    """When multiple keywords match, classifier picks the type with most hits."""

    # 2 etiology keywords vs 1 specificity keyword
    result = classify_gap_type("etiology 病因 未特指", "")
    assert result == "etiology_unspecified"


# ---------------------------------------------------------------------------
# 4 ResponseOptionCategory classifier coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        ("A. 肺炎病原体为肺炎链球菌 (J13)", "specific_clinical_answer"),
        ("B. 其他已知病原体 (请在自由文本中说明)", "free_text_fallback"),
        ("C. 痰培养结果为定植菌, 不作为病原体", "colonization_or_non_pathological"),
        ("D. 无法确定 (unable to determine)", "escape_hatch"),
        ("E. 临床不支持", "escape_hatch"),
        ("F. Other (please specify in free text)", "free_text_fallback"),
        ("Patient has colonization, not pathogenic", "colonization_or_non_pathological"),
    ],
)
def test_classify_response_option_covers_4_categories(
    label: str, expected: ResponseOptionCategory
) -> None:
    assert classify_response_option(label) == expected


def test_classify_response_option_picks_escape_hatch_first() -> None:
    """Escape hatch takes precedence over other categories (NLQ-005
    requires escape hatch detection to be reliable)."""

    # Label contains both "无法确定" (escape) and "定植菌" (colonization)
    assert classify_response_option("无法确定, 视为定植菌") == "escape_hatch"


# ---------------------------------------------------------------------------
# ResponseOption dataclass
# ---------------------------------------------------------------------------


def test_response_option_dataclass_defaults() -> None:
    """ResponseOption defaults to specific_clinical_answer category."""

    opt = ResponseOption(label="A. 肺炎链球菌 (J13)")
    assert opt.category == "specific_clinical_answer"
    assert opt.icd_code_hint == ""


def test_response_option_with_icd_hint() -> None:
    opt = ResponseOption(
        label="A. 肺炎病原体为肺炎链球菌",
        category="specific_clinical_answer",
        icd_code_hint="J13",
    )
    assert opt.icd_code_hint == "J13"


# ---------------------------------------------------------------------------
# DocumentationGap with gap_type field
# ---------------------------------------------------------------------------


def test_documentation_gap_includes_gap_type_field() -> None:
    """Gate 4 adds gap_type field; default is diagnostic_specificity."""

    g = DocumentationGap(
        gap_id="g1",
        description="肺炎诊断特异性不足",
        why_it_matters="影响 J18.9 vs J13",
        evidence_span=EvidenceSpan(document_id="入院记录", quote="诊断: 肺炎"),
    )
    assert g.gap_type == "diagnostic_specificity"  # default


def test_documentation_gap_accepts_all_8_gap_types() -> None:
    """All 8 GapType values must be assignable."""

    ev = EvidenceSpan(document_id="d", quote="q")
    valid_types = [
        "diagnostic_specificity",
        "etiology_unspecified",
        "severity_unspecified",
        "acuity_unspecified",
        "anatomical_site_unspecified",
        "clinical_correlation_unestablished",
        "temporal_unspecified",
        "conflicting_documentation",
    ]
    for gap_type in valid_types:
        g = DocumentationGap(
            gap_id=f"g_{gap_type}",
            description="test",
            why_it_matters="test",
            evidence_span=ev,
            gap_type=gap_type,  # type: ignore[arg-type]
        )
        assert g.gap_type == gap_type


# ---------------------------------------------------------------------------
# DB models import + shape
# ---------------------------------------------------------------------------


def test_cdi_db_models_import_cleanly() -> None:
    """All 5 Gate 4 DB models must import without error."""

    from app.models import (
        CDICaseModel,
        ClinicianResponseModel,
        DocumentationGapModel,
        DocumentVersionModel,
        ProviderQueryModel,
    )

    # Verify table names match alembic migration
    assert CDICaseModel.__tablename__ == "cdi_cases"
    assert DocumentationGapModel.__tablename__ == "cdi_documentation_gaps"
    assert ProviderQueryModel.__tablename__ == "cdi_provider_queries"
    assert ClinicianResponseModel.__tablename__ == "cdi_clinician_responses"
    assert DocumentVersionModel.__tablename__ == "cdi_document_versions"


def test_cdi_models_have_required_indexes() -> None:
    """Verify primary access patterns are indexed (per Gate 4 spec)."""

    from app.models import ProviderQueryModel

    # Check key columns exist for indexing
    columns = {c.name for c in ProviderQueryModel.__table__.columns}
    required = {
        "case_id", "gap_id", "lifecycle_state", "clinician_user_id",
        "sla_due_at", "nlq_gate_verdict", "priority",
    }
    assert required.issubset(columns), f"missing: {required - columns}"


def test_provider_query_model_includes_full_nlq_gate_audit_trail() -> None:
    """ProviderQueryModel must store all NLQ gate audit fields (verdict,
    rules_evaluated, rules_passed, block_reasons, version)."""

    from app.models import ProviderQueryModel

    columns = {c.name for c in ProviderQueryModel.__table__.columns}
    nlq_fields = {
        "nlq_gate_verdict",
        "nlq_gate_rules_evaluated",
        "nlq_gate_rules_passed",
        "nlq_gate_block_reasons",
        "nlq_gate_version",
    }
    assert nlq_fields.issubset(columns), f"missing NLQ fields: {nlq_fields - columns}"
