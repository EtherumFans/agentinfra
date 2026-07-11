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
    "unknown",
]
"""9 CDI gap types per PDF §6.2 + Phase 5 Track D P0 Gate 4 'unknown' bucket.

The 'unknown' bucket catches gap descriptions the LLM cannot confidently
classify. ``classify_gap_type`` returns 'unknown' when
``classification_confidence`` falls below the threshold (no keyword hits
AND no LLM-provided gap_type).

diagnostic_specificity         — 肺炎 vs 细菌性肺炎 (J18.9 vs J13)
etiology_unspecified           — 急性肾损伤 病因未记录
severity_unspecified           — 慢性肾病 严重程度未记录 (CKD stage missing)
acuity_unspecified             — 急慢性未区分 (acute vs chronic)
anatomical_site_unspecified    — 部位未明确 (left vs right, T12 vs L1)
clinical_correlation_unestablished — 痰培养 vs 临床表现 关联未建立
temporal_unspecified           — 时间关系未明确 (术后第几天发热)
conflicting_documentation      — 入院诊断 vs 出院诊断 不一致
unknown                        — Phase 5 Track D P0 Gate 4: classifier fallback
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


# Phase 5 Track D P0.5 Gate 4 — Claim-Evidence alignment taxonomy
SupportType = Literal["direct", "contextual", "inferred", "unsupported"]
"""Per Master Task §5.3. How a Claim's evidence relates to chart reality.

direct       — chart verbatim supports the claim
contextual   — context required, no new clinical conclusion
inferred     — reasonable inference, NOT a determinate fact
unsupported  — no chart evidence
"""

ClaimCriticality = Literal["critical", "supporting"]
"""critical — load-bearing for the query's existence (must have evidence)
supporting — auxiliary context (gap may still survive without)
"""

ClaimValidationStatus = Literal[
    "unchecked",
    "valid",
    "invalid_quote",
    "invalid_span",
    "negation_as_support",
    "pmh_as_current",
    "inferred_as_direct",
    "no_evidence",
    "cross_case_evidence",
]
"""Deterministic validation outcome for a Claim-Evidence pair (CEA-001..009)."""


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


def classify_gap_type(
    description: str,
    why_it_matters: str = "",
) -> GapType:
    """Classify a free-text gap description into one of 9 GapTypes.

    Phase 5 Track D P0 Gate 4: fallback is now ``unknown`` (was
    ``diagnostic_specificity``). The ``unknown`` bucket surfaces LLM
    uncertainty to the audit trail instead of silently mis-tagging gaps
    that the classifier cannot confidently place.

    Picks the GapType whose keywords appear most frequently in
    description+why_it_matters. On ties or empty input → ``unknown``.

    For confidence scores, see ``classify_gap_type_with_confidence``.
    """

    gap_type, _ = classify_gap_type_with_confidence(description, why_it_matters)
    return gap_type


def classify_gap_type_with_confidence(
    description: str,
    why_it_matters: str = "",
) -> tuple[GapType, float]:
    """Classify a gap and return ``(gap_type, confidence)``.

    Confidence = best_score / max(1, total_keyword_hits) in [0.0, 1.0].
    Returns ``("unknown", 0.0)`` when no keywords match.
    """

    if not description and not why_it_matters:
        return "unknown", 0.0
    text = (description + " " + why_it_matters).lower()
    scores: dict[str, int] = {}
    for gap_type, keywords in _GAP_TYPE_KEYWORDS.items():
        scores[gap_type] = sum(1 for kw in keywords if kw.lower() in text)
    best_gap_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score == 0:
        return "unknown", 0.0
    total_hits = sum(scores.values())
    confidence = float(best_score) / float(max(1, total_hits))
    return best_gap_type, confidence  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Evidence primitives (chart-anchored)
# ---------------------------------------------------------------------------


@dataclass
class EvidenceSpan:
    """Character-anchored evidence quote from a chart document.

    Required by red line ``chart_evidence_required`` — every gap and every
    query must cite one.

    Phase 5 Track D P0 Gate 4 — multi-evidence Claim-Evidence alignment:
        ``supports_claim`` is set by the alignment checker to indicate
        whether this span actually substantiates the gap's claim. A gap
        with 0 supporting spans is downgraded to ``unknown`` bucket.
    """

    document_id: str
    quote: str
    char_start: int = 0
    char_end: int = 0
    documented_at: str = ""
    supports_claim: bool | None = None  # None = unchecked; True = aligned; False = contradicting


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
    # Phase 5 Track D P0 Gate 4: multi-evidence + unknown bucket
    evidence_spans: list[EvidenceSpan] = field(default_factory=list)
    classification_confidence: float = 1.0  # 0.0 = no signal, 1.0 = LLM-tagged


def claim_evidence_alignment_score(gap: DocumentationGap) -> float:
    """Return the fraction of evidence_spans that support the gap's claim.

    Phase 5 Track D P0 Gate 4 / PDF §A5 (multi-evidence alignment).

    Returns 1.0 when ``evidence_spans`` is empty (deferred to legacy
    single-span ``evidence_span``). Otherwise computes:
        aligned_spans / total_checked_spans

    Spans with ``supports_claim=None`` (unchecked) are excluded from the
    denominator. If no span has been checked, returns 1.0.
    """

    spans = gap.evidence_spans or ([gap.evidence_span] if gap.evidence_span.quote else [])
    if not spans:
        return 0.0
    checked = [s for s in spans if s.supports_claim is not None]
    if not checked:
        return 1.0
    aligned = sum(1 for s in checked if s.supports_claim is True)
    return aligned / len(checked)


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
    # Phase 5 Track D P0.5 Gate 4 — Claim-Evidence alignment
    claims: list["Claim"] = field(default_factory=list)
    claim_evidence_alignments: list["ClaimEvidenceAlignment"] = field(default_factory=list)
    # Phase 5 Track D P0.5 Gate 4 — Semantic necessity verdict
    semantic_necessity_verdict: str = ""  # "PASS" | "REVIEW_REQUIRED" | "BLOCK" | "DEGRADED"
    semantic_necessity_reason_codes: list[str] = field(default_factory=list)
    semantic_necessity_degraded: bool = False


# ---------------------------------------------------------------------------
# Phase 5 Track D P0.5 Gate 4 — Claim + Claim-Evidence alignment primitives
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """One clinical claim asserted by a Provider Query.

    Per Master Task §5.2 — every query decomposes into ≥1 atomic claim.
    The query is BLOCKED if a critical claim has no chart evidence.

    The LLM extraction stage (``claim_evidence_gate.extract_claims``) is
    responsible for splitting a query like::

        "患者入院前发病3天，痰培养检出肺炎链球菌，当前诊断为肺炎"

    into 3 claims:
      - claim_1: "患者入院前发病3天"           (critical=False)
      - claim_2: "痰培养检出肺炎链球菌"         (critical=True)
      - claim_3: "当前诊断为肺炎"              (critical=True)
    """

    claim_id: str
    text: str
    criticality: ClaimCriticality = "supporting"


@dataclass
class ClaimEvidenceAlignment:
    """Mapping between one Claim and one EvidenceSpan, with deterministic
    validation outcome.

    Per Master Task §5.3. ``support_type`` is the semantic axis (how the
    evidence relates to the claim). ``validation_status`` is the
    deterministic validation outcome (CEA-001..009 rules).
    """

    claim_id: str
    evidence_span_id: str  # references EvidenceSpan.quote hash (or "gap:{gap_id}:default")
    document_id: str
    quote: str
    char_start: int = -1
    char_end: int = -1
    support_type: SupportType = "unsupported"
    confidence: float = 0.0
    validation_status: ClaimValidationStatus = "unchecked"


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
    "claim_evidence_alignment_score",
    "classify_gap_type_with_confidence",
    # Phase 5 Track D P0.5 Gate 4
    "SupportType",
    "ClaimCriticality",
    "ClaimValidationStatus",
    "Claim",
    "ClaimEvidenceAlignment",
]
