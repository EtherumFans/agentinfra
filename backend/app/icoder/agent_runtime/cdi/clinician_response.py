"""CDI Clinician Response Workflow (Phase 5 Track D Gate 6).

This module handles the physician-side of the CDI loop:
    - Capturing clinician responses to Provider Queries
    - Driving DOCUMENTATION_UPDATED transition after response
    - Computing CDI revalidation (whether the response closed the gap)
    - Coordinating with DocumentVersion snapshots for before/after diff

It complements ``cdi_query_lifecycle.py`` (which drives the state
machine) by adding the response-handling logic.

Pure logic — no HTTP/DB layer here. Gate 9 wires it to REST API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from app.icoder.agent_runtime.cdi import (
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
    classify_response_option,
)
from app.services.cdi_query_lifecycle import (
    TransitionResult,
    attempt_transition,
)


# ---------------------------------------------------------------------------
# Response value (what the clinician submitted)
# ---------------------------------------------------------------------------


@dataclass
class ClinicianResponseValue:
    """The clinician's response to a Provider Query."""

    selected_option: str
    free_text: str = ""
    response_metadata: dict = field(default_factory=dict)
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def category(self) -> Literal[
        "specific_clinical_answer",
        "free_text_fallback",
        "colonization_or_non_pathological",
        "escape_hatch",
    ]:
        """Categorize the response for downstream handling."""

        return classify_response_option(self.selected_option)


# ---------------------------------------------------------------------------
# Revalidation outcome (did the response close the gap?)
# ---------------------------------------------------------------------------


RevalidationOutcome = Literal[
    "GAP_CLOSED",
    "GAP_PARTIALLY_CLOSED",
    "GAP_STILL_OPEN",
    "NEW_GAP_RAISED",
    "RESPONSE_REJECTED",
]


@dataclass
class RevalidationResult:
    """Outcome of running CDI again against the post-clarification chart."""

    outcome: RevalidationOutcome
    closed_gap_ids: list[str] = field(default_factory=list)
    new_gap_ids: list[str] = field(default_factory=list)
    rationale: str = ""
    revalidation_run_id: str = ""


# ---------------------------------------------------------------------------
# Response workflow
# ---------------------------------------------------------------------------


def process_clinician_response(
    query: ProviderQuery,
    response: ClinicianResponseValue,
    *,
    now: datetime | None = None,
) -> tuple[TransitionResult, TransitionResult | None]:
    """Process a clinician's response and drive the lifecycle forward.

    Sequence:
        1. VIEWED → RESPONDED (record the response)
        2. RESPONDED → DOCUMENTATION_UPDATED (only if response is actionable)

    If the response category is ``escape_hatch`` (clinician unable to
    determine), the query moves to ESCALATED instead of
    DOCUMENTATION_UPDATED because no documentation change is expected.

    Returns ``(viewed_to_responded_result, responded_to_next_result_or_None)``.
    Caller persists the transitions + the ClinicianResponseModel row.
    """

    if now is None:
        now = datetime.now(timezone.utc)

    # 1. VIEWED → RESPONDED
    r1 = attempt_transition(
        from_state="VIEWED",
        to_state="RESPONDED",
        now=now,
    )

    if not r1.accepted:
        return r1, None

    # 2. Decide next state based on response category
    if response.category == "escape_hatch":
        # Clinician unable to determine — escalate, do NOT modify chart
        r2 = attempt_transition(
            from_state="RESPONDED",
            to_state="ESCALATED",
            now=now,
        )
        return r1, r2

    # Otherwise, advance to DOCUMENTATION_UPDATED (chart will be revised)
    r2 = attempt_transition(
        from_state="RESPONDED",
        to_state="DOCUMENTATION_UPDATED",
        now=now,
    )
    return r1, r2


def revalidate_gap(
    gap: DocumentationGap,
    response: ClinicianResponseValue,
    *,
    revalidation_run_id: str = "",
) -> RevalidationResult:
    """Decide whether a gap is closed by the clinician's response.

    This is a heuristic for the orchestrator. The real implementation
    in Gate 6+ re-runs the CDI LLM against the updated chart; here we
    use response category + selected option matching as a fast stub.
    """

    # Escape hatch → can't close gap, needs human follow-up
    if response.category == "escape_hatch":
        return RevalidationResult(
            outcome="RESPONSE_REJECTED",
            rationale="clinician selected escape hatch; gap cannot be auto-closed",
            revalidation_run_id=revalidation_run_id,
        )

    # Free-text fallback → need LLM to parse, mark partial
    if response.category == "free_text_fallback":
        return RevalidationResult(
            outcome="GAP_PARTIALLY_CLOSED",
            rationale="clinician provided free-text response; requires LLM validation",
            revalidation_run_id=revalidation_run_id,
        )

    # Colonization → lab result rejected, gap likely still open with revised scope
    if response.category == "colonization_or_non_pathological":
        return RevalidationResult(
            outcome="GAP_STILL_OPEN",
            rationale="clinician indicated lab result is not pathologically relevant",
            revalidation_run_id=revalidation_run_id,
        )

    # specific_clinical_answer → check if it references the gap's clarification target
    needed = (gap.minimal_clarification_needed or "").lower()
    selected = response.selected_option.lower()
    if needed and any(token in selected for token in needed.split() if len(token) > 1):
        return RevalidationResult(
            outcome="GAP_CLOSED",
            closed_gap_ids=[gap.gap_id],
            rationale="clinician's selected option addresses the minimal clarification needed",
            revalidation_run_id=revalidation_run_id,
        )

    return RevalidationResult(
        outcome="GAP_CLOSED",
        closed_gap_ids=[gap.gap_id],
        rationale="specific clinical answer provided; gap closed pending chart writeback",
        revalidation_run_id=revalidation_run_id,
    )


# ---------------------------------------------------------------------------
# Document diff helper
# ---------------------------------------------------------------------------


@dataclass
class DocumentDiff:
    """Summary of changes between two document versions."""

    document_id: str
    added_sections: list[str] = field(default_factory=list)
    modified_spans: list[dict] = field(default_factory=list)
    content_hash_before: str = ""
    content_hash_after: str = ""
    diff_summary: dict = field(default_factory=dict)


def compute_document_diff(
    document_id: str,
    before_text: str,
    after_text: str,
) -> DocumentDiff:
    """Compute a structural diff between two versions of a chart document.

    Real implementation (Gate 7 UI) uses difflib for span-level diff.
    For Gate 6 we emit the metadata (hashes + lengths) — enough for DB
    persistence and the audit trail.
    """

    import hashlib

    h_before = hashlib.sha256(before_text.encode("utf-8")).hexdigest()
    h_after = hashlib.sha256(after_text.encode("utf-8")).hexdigest()

    diff = DocumentDiff(
        document_id=document_id,
        content_hash_before=h_before,
        content_hash_after=h_after,
    )
    if h_before != h_after:
        diff.diff_summary = {
            "before_length": len(before_text),
            "after_length": len(after_text),
            "delta_chars": len(after_text) - len(before_text),
        }
    else:
        diff.diff_summary = {"unchanged": True}
    return diff


__all__ = [
    "ClinicianResponseValue",
    "DocumentDiff",
    "RevalidationOutcome",
    "RevalidationResult",
    "compute_document_diff",
    "process_clinician_response",
    "revalidate_gap",
]
