"""CDI domain models (Phase 5 Track D Gate 4 — full China CDI capability model).

This module extends the Gate 3 slice with:
    - 8 gap types per PDF §6.2 (diagnostic_specificity, etiology_unspecified,
      severity_unspecified, acuity_unspecified, anatomical_site_unspecified,
      clinical_correlation_unestablished, temporal_unspecified,
      conflicting_documentation)
    - 4 risk flag categories
    - 4 document types
    - Response option taxonomy (4 categories per Gate 2 audit)
    - Classifier helper (free-text → gap_type) for the orchestrator

PDF §6 Gate 4 reference:
    reports/phase5_track_d/GATE4_DOMAIN_MODEL_REPORT.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Enums (string-based for JSON compatibility)
# ---------------------------------------------------------------------------


GapType = Literal[
    "diagnostic_specificity",
    "etiology_unspecified",
    "severity_unspecified",
    "acuity_unspecified",
    "anatomical_site_unspecified",
    "clinical_correlation_unestablished",
    "temporal_unspecified",
    "conflicting_documentation",
]
"""8 CDI gap types per PDF §6.2.

diagnostic_specificity         — 肺炎 vs 细菌性肺炎 (J18.9 vs J13)
etiology_unspecified           — 急性肾损伤 病因未记录
severity_unspecified           — 慢性肾病 严重程度未记录 (CKD stage missing)
acuity_unspecified             — 急慢性未区分 (acute vs chronic)
anatomical_site_unspecified    — 部位未明确 (left vs right, T12 vs L1)
clinical_correlation_unestablished — 痰培养 vs 临床表现 关联未建立
temporal_unspecified           — 时间关系未明确 (术后第几天发热)
conflicting_documentation      — 入院诊断 vs 出院诊断 不一致
"""


RiskFlagCategory = Literal[
    "contradiction",
    "unsupported_diagnosis",
    "ambiguous_term",
    "copied_forward_indicator",
]


DocumentType = Literal[
    "admission_note",
    "progress_note",
    "discharge_summary",
    "lab_report",
    "imaging_report",
    "operative_report",
    "nursing_note",
    "other",
]


ResponseOptionCategory = Literal[
    "specific_clinical_answer",
    "free_text_fallback",
    "colonization_or_non_pathological",
    "escape_hatch",
]
"""Per Gate 2 audit (CORTI_CDI_PROVIDER_QUERY_AUDIT.md §7).
A compliant query must include ≥1 escape_hatch (NLQ-005)."""


# ---------------------------------------------------------------------------
# Response option helper
# ---------------------------------------------------------------------------


@dataclass
class ResponseOption:
    """One option in a Provider Query's response_options array."""

    label: str  # e.g. "A. 肺炎病原体为肺炎链球菌 (J13)"
    category: ResponseOptionCategory = "specific_clinical_answer"
    icd_code_hint: str = ""


def classify_response_option(label: str) -> ResponseOptionCategory:
    """Classify a response option label into one of 4 categories.

    Used by the orchestrator to verify escape hatch presence (NLQ-005).
    """
    low = label.lower()
    escape_markers = [
        "无法确定", "临床不支持", "尚难确定", "无法判断",
        "unable to determine", "clinically undetermined", "indeterminate",
        "not applicable",
    ]
    colonization_markers = [
        "定植菌", "不作为病原体", "colonization", "not pathogenic",
    ]
    free_text_markers = [
        "请在自由文本", "请说明", "其他已知", "free text", "other (please specify",
    ]
    if any(m in low for m in escape_markers):
        return "escape_hatch"
    if any(m in low for m in colonization_markers):
        return "colonization_or_non_pathological"
    if any(m in low for m in free_text_markers):
        return "free_text_fallback"
    return "specific_clinical_answer"


# ---------------------------------------------------------------------------
# Gap classifier (orchestrator helper)
# ---------------------------------------------------------------------------

_GAP_TYPE_KEYWORDS: dict[GapType, tuple[str, ...]] = {
    "diagnostic_specificity": (
        "特异性", "病原体", "specificity",
    ),
    "etiology_unspecified": (
        "病因", "etiology", "cause of",
    ),
    "severity_unspecified": (
        "严重程度", "分级", "stage", "severity", "grade",
    ),
    "acuity_unspecified": (
        "急性", "慢性", "急慢性", "acute", "chronic",
    ),
    "anatomical_site_unspecified": (
        "部位", "左侧", "右侧", "site", "laterality",
    ),
    "clinical_correlation_unestablished": (
        "临床关联", "临床不符", "clinical correlation", "correlation",
    ),
    "temporal_unspecified": (
        "时间关系", "术后", "temporal", "timing",
    ),
    "conflicting_documentation": (
        "冲突", "不一致", "矛盾", "conflict", "contradiction",
    ),
}


def classify_gap_type(description: str, why_it_matters: str = "") -> GapType:
    """Classify a free-text gap description into one of 8 GapTypes.

    The orchestrator uses this when the LLM doesn't tag gap_type itself.
    Picks the GapType whose keywords appear most frequently in
    description+why_it_matters. Defaults to ``diagnostic_specificity``
    (the most common CDI gap type) on ties or empty input.
    """

    if not description and not why_it_matters:
        return "diagnostic_specificity"
    text = (description + " " + why_it_matters).lower()
    scores: dict[str, int] = {}
    for gap_type, keywords in _GAP_TYPE_KEYWORDS.items():
        scores[gap_type] = sum(1 for kw in keywords if kw.lower() in text)
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] == 0:
        return "diagnostic_specificity"
    return best[0]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Evidence primitives (chart-anchored)
# ---------------------------------------------------------------------------


@dataclass
class EvidenceSpan:
    """Character-anchored evidence quote from a chart document.

    Required by red line ``chart_evidence_required`` — every gap and every
    query must cite one.
    """

    document_id: str
    quote: str
    char_start: int = 0
    char_end: int = 0
    documented_at: str = ""


# ---------------------------------------------------------------------------
# Encounter synthesis
# ---------------------------------------------------------------------------


@dataclass
class EncounterSummary:
    """Section 1 of Corti-compatible CDI output."""

    key_points: list[str] = field(default_factory=list)
    encounter_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Documentation gaps (Section 2)
# ---------------------------------------------------------------------------


@dataclass
class DocumentationGap:
    """A single documentation gap identified by the CDI agent."""

    gap_id: str
    description: str
    why_it_matters: str
    evidence_span: EvidenceSpan
    gap_type: GapType = "diagnostic_specificity"
    minimal_clarification_needed: str = ""
    priority: Literal["routine", "urgent"] = "routine"
    linked_query_id: str = ""


# ---------------------------------------------------------------------------
# Provider queries (Section 3) — full shape, NLQ-gate-compatible
# ---------------------------------------------------------------------------


@dataclass
class ProviderQuery:
    """A single Provider Query (Non-leading, evidence-grounded)."""

    query_id: str
    gap_id: str
    topic: str
    reason: str
    evidence_span: EvidenceSpan
    query_text: str
    response_options: list[str] = field(default_factory=list)
    priority: Literal["routine", "urgent"] = "routine"
    lifecycle_state: Literal[
        "DRAFT",
        "PENDING_CDI_REVIEW",
        "APPROVED",
        "SENT_TO_CLINICIAN",
        "VIEWED",
        "RESPONDED",
        "DOCUMENTATION_UPDATED",
        "REVALIDATED",
        "CLOSED",
        "CANCELLED",
        "ESCALATED",
        "EXPIRED",
    ] = "DRAFT"
    nlq_gate_verdict: str = ""
    nlq_gate_block_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Coding specificity checklist (Section 4)
# ---------------------------------------------------------------------------


@dataclass
class CodingSpecificityItem:
    condition: str
    elements_to_address: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk flags (Section 5)
# ---------------------------------------------------------------------------


@dataclass
class RiskFlag:
    category: Literal[
        "contradiction",
        "unsupported_diagnosis",
        "ambiguous_term",
        "copied_forward_indicator",
    ]
    description: str
    evidence_span: EvidenceSpan | None = None


# ---------------------------------------------------------------------------
# Specialist trace (Section 6)
# ---------------------------------------------------------------------------


@dataclass
class SpecialistTraceEntry:
    expert_id: str
    consulted: bool
    requested: str = ""
    accepted: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Top-level CDI case state
# ---------------------------------------------------------------------------


@dataclass
class CDICase:
    """Top-level CDI case state. The orchestrator threads this through stages."""

    case_id: str
    patient_ref: str = ""
    encounter_ref: str = ""
    chart_excerpt: str = ""
    encounter_metadata: dict[str, Any] = field(default_factory=dict)
    draft_codes: list[str] = field(default_factory=list)

    # Stage outputs (filled in by orchestrator)
    encounter_summary: EncounterSummary | None = None
    documentation_gaps: list[DocumentationGap] = field(default_factory=list)
    proposed_provider_queries: list[ProviderQuery] = field(default_factory=list)
    coding_specificity_checklist: list[CodingSpecificityItem] = field(default_factory=list)
    risk_flags: list[RiskFlag] = field(default_factory=list)
    specialist_trace: list[SpecialistTraceEntry] = field(default_factory=list)

    # Final state
    completion_state: Literal[
        "AUTO_PASS",
        "REVIEW_RECOMMENDED",
        "REVIEW_REQUIRED",
        "BLOCKED",
    ] = "REVIEW_REQUIRED"
    stage_run_ids: dict[str, str] = field(default_factory=dict)
    stage_trace_ids: dict[str, str] = field(default_factory=dict)


__all__ = [
    "EvidenceSpan",
    "EncounterSummary",
    "DocumentationGap",
    "ProviderQuery",
    "CodingSpecificityItem",
    "RiskFlag",
    "SpecialistTraceEntry",
    "CDICase",
]
