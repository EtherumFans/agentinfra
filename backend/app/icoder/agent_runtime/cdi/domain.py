"""CDI domain models (Phase 5 Track D Gate 4 — minimal slice for Gate 3).

This is a deliberately minimal domain slice. The full schema (with
Pydantic validators, DB persistence, etc.) is added in Gate 4 / Gate 5.
Gate 3 needs just enough shape to:
    1. Let the orchestrator run end-to-end on a stub runner
    2. Let the NLQ gate consume a ``ProviderQuery``
    3. Let tests verify the runtime is callable

Track D PDF §5/§6/§7 specify the full schema; this file will grow
significantly in subsequent gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
