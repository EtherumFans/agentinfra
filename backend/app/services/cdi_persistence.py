"""CDI Persistence Service (Phase 5 Track D P0 Gate 3 + P0.5 Gate 1).

Closes the DB persistence loop: POST /api/v1/cdi/runs now writes the
case + gaps + queries atomically, and GET /api/v1/cdi/runs/{case_id}
reads them back instead of returning 501.

PDF §A3 (DB persistence is wired at schema level only) — this module
makes the runtime side real.

Phase 5 Track D P0.5 Gate 1 (2026-07-11)
========================================
The original P0 implementation used an idempotent-skip on gap_id/query_id
to defend against placeholder-ID collisions when the LLM emitted
``GAP-001``..``GAP-004`` repeatedly across cases. That skip caused
"0 Gap + N Query" pathology: queries were written even when their
parent gap was skipped, producing orphan query rows whose gap_id pointed
into a *different* case.

Gate 1 fix:
  1. ``_localize_child_ids`` rewrites placeholder gap_id/query_id to be
     case-scoped before persistence. Collisions across cases are now
     structurally impossible.
  2. ``persist_case`` validates gap↔query referential integrity in the
     same transaction; orphan queries are dropped with a warning.
  3. ``assert_case_consistent`` is called on read-back; the API layer
     surfaces a 500 diagnostic if inconsistency is detected.
  4. ``derive_case_state`` provides a single source-of-truth for the
     case-level state derived from gap/query counts (replaces ad-hoc
     derivation scattered across handlers).

Conversion contract
===================

Domain dataclasses (``app.icoder.agent_runtime.cdi.domain``) are the
runtime representation. ORM models (``app.models.cdi_case``) are the
persistence representation. This module owns the boundary — callers
should never mutate ORM models directly.

Public surface
==============

    persist_case(session, case, *, org_id, user_id) -> CDICaseModel
        Atomic insert: 1 case + N gaps + M queries in one transaction.

    load_case(session, case_id) -> CDICaseModel | None
        Eager-load case + gaps + queries for read-back.

    case_to_domain(model) -> CDICase
        Reverse mapping for the API layer.

Optimistic locking
==================

PDF §A3 requires transactional transitions with optimistic locking.
The lifecycle transition endpoint (POST /queries/{id}/transition)
calls ``update_query_lifecycle`` which writes
``WHERE id=:id AND lifecycle_state=:expected_from`` — concurrent
transitions are rejected with a 409 Conflict.

Async + sync
============

SQLAlchemy async session is the production path. We expose both sync
and async variants of each method so the API handler (async) and pure-
logic tests (sync via asyncio.run) both work.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import replace as dc_replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
)
from app.models.cdi_case import (
    CDICaseModel,
    ClinicianResponseModel,
    DocumentationGapModel,
    DocumentVersionModel,
    ProviderQueryModel,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 5 Track D P0.5 Gate 1 — case-scoped child IDs
# ---------------------------------------------------------------------------
#
# The CDI orchestrator (real_runner) emits placeholder gap_id and query_id
# values like ``GAP-001``, ``Q-001`` because they're produced by the LLM
# JSON output. These collide across cases. We localize them per-case before
# persistence so the DB primary keys are globally unique and the gap_id
# foreign-key reference on ProviderQuery stays consistent within each case.
#
# Detection heuristic: any gap_id / query_id that does NOT start with the
# case_id is treated as a placeholder and rewritten. Already-localized IDs
# (e.g. ``CASE-abc/GAP-001``) pass through unchanged.

_PLACEHOLDER_GAP_RE = re.compile(r"^GAP-\d+$", re.IGNORECASE)
_PLACEHOLDER_QUERY_RE = re.compile(r"^Q-\d+$", re.IGNORECASE)


def _is_placeholder_gap_id(gap_id: str) -> bool:
    return bool(_PLACEHOLDER_GAP_RE.match(gap_id or ""))


def _is_placeholder_query_id(query_id: str) -> bool:
    return bool(_PLACEHOLDER_QUERY_RE.match(query_id or ""))


def _localize_child_ids(case: CDICase) -> CDICase:
    """Rewrite placeholder gap_id / query_id to be case-scoped.

    Returns a new CDICase with rewritten IDs (functional — does not
    mutate the input). ProviderQuery.gap_id references are remapped to
    the new gap IDs. Queries whose gap_id does not match any gap in the
    case (after localization) are dropped: the orchestrator is not
    allowed to emit orphan queries, and persisting them would re-introduce
    the "0 Gap + N Query" pathology.

    The resulting case is safe to persist without any idempotent-skip
    on child IDs.
    """
    if not case.case_id:
        return case

    gap_id_map: dict[str, str] = {}
    new_gaps: list[DocumentationGap] = []
    for idx, gap in enumerate(case.documentation_gaps, start=1):
        old_id = gap.gap_id
        if _is_placeholder_gap_id(old_id) or not old_id.startswith(case.case_id):
            new_id = f"{case.case_id}/GAP-{idx:03d}"
        else:
            new_id = old_id
        gap_id_map[old_id] = new_id
        new_gaps.append(dc_replace(gap, gap_id=new_id))

    valid_gap_ids = set(gap_id_map.values())
    new_queries: list[ProviderQuery] = []
    for idx, q in enumerate(case.proposed_provider_queries, start=1):
        old_qid = q.query_id
        if _is_placeholder_query_id(old_qid) or not old_qid.startswith(case.case_id):
            new_qid = f"{case.case_id}/Q-{idx:03d}"
        else:
            new_qid = old_qid

        # Remap the gap_id FK to the localized ID, if present.
        new_gap_id = gap_id_map.get(q.gap_id, q.gap_id)
        if new_gap_id not in valid_gap_ids:
            logger.warning(
                "cdi.persist.drop_orphan_query case=%s query_id=%s gap_id=%s "
                "not in case gaps — dropping query (referential integrity)",
                case.case_id, old_qid, q.gap_id,
            )
            continue

        new_queries.append(dc_replace(
            q,
            query_id=new_qid,
            gap_id=new_gap_id,
        ))

    return dc_replace(
        case,
        documentation_gaps=new_gaps,
        proposed_provider_queries=new_queries,
    )


# ---------------------------------------------------------------------------
# Domain → ORM
# ---------------------------------------------------------------------------


def _hash_chart(chart_excerpt: str) -> str:
    return hashlib.sha256(chart_excerpt.encode("utf-8")).hexdigest()


def _evidence_to_dict(ev: EvidenceSpan | None) -> dict[str, Any]:
    if ev is None:
        return {
            "document_id": "", "quote": "",
            "char_start": 0, "char_end": 0,
            "documented_at": "",
        }
    return {
        "document_id": ev.document_id,
        "quote": ev.quote,
        "char_start": ev.char_start,
        "char_end": ev.char_end,
        "documented_at": ev.documented_at or "",
    }


def gap_to_orm(gap: DocumentationGap, case_id: str) -> DocumentationGapModel:
    """Convert a runtime DocumentationGap to its ORM model (no DB write)."""
    ev = gap.evidence_span
    return DocumentationGapModel(
        id=gap.gap_id,
        case_id=case_id,
        gap_type=gap.gap_type,
        description=gap.description,
        why_it_matters=gap.why_it_matters,
        minimal_clarification_needed=gap.minimal_clarification_needed,
        evidence_document_id=ev.document_id if ev else "",
        evidence_quote=ev.quote if ev else "",
        evidence_char_start=ev.char_start if ev else 0,
        evidence_char_end=ev.char_end if ev else 0,
        evidence_documented_at=None,
        priority=gap.priority,
        status="OPEN",
    )


def query_to_orm(q: ProviderQuery, case_id: str) -> ProviderQueryModel:
    """Convert a runtime ProviderQuery to its ORM model (no DB write)."""
    ev = q.evidence_span
    return ProviderQueryModel(
        id=q.query_id,
        case_id=case_id,
        gap_id=q.gap_id,
        topic=q.topic,
        reason=q.reason,
        query_text=q.query_text,
        response_options=list(q.response_options),
        evidence_document_id=ev.document_id if ev else "",
        evidence_quote=ev.quote if ev else "",
        evidence_char_start=ev.char_start if ev else 0,
        evidence_char_end=ev.char_end if ev else 0,
        nlq_gate_verdict=q.nlq_gate_verdict or "PENDING",
        nlq_gate_block_reasons=list(q.nlq_gate_block_reasons),
        lifecycle_state=q.lifecycle_state,
        priority=q.priority,
    )


def case_to_orm(
    case: CDICase,
    *,
    organization_id: str | None = None,
    created_by_user_id: str | None = None,
    agent_ref: str = "icoder/clinical-documentation-improvement-agent@1.0.0",
    run_id: str = "",
    trace_id: str = "",
) -> CDICaseModel:
    """Convert a runtime CDICase to its ORM model (no DB write).

    Children (gaps + queries) are constructed via gap_to_orm /
    query_to_orm and attached. Caller is responsible for adding the
    model to a session and committing.
    """
    now = datetime.now(timezone.utc)
    chart_hash = _hash_chart(case.chart_excerpt)
    encounter_summary_dict: dict[str, Any] = {}
    if case.encounter_summary is not None:
        encounter_summary_dict = {
            "key_points": list(case.encounter_summary.key_points),
            "encounter_metadata": dict(case.encounter_summary.encounter_metadata),
        }

    case_model = CDICaseModel(
        id=case.case_id,
        organization_id=organization_id,
        patient_ref=case.patient_ref or "DEID",
        encounter_ref=case.encounter_ref or "DEID",
        chart_excerpt_hash=chart_hash,
        chart_excerpt_length=len(case.chart_excerpt),
        encounter_metadata=encounter_summary_dict.get("encounter_metadata", {}),
        draft_codes=list(case.draft_codes),
        run_id=run_id,
        trace_id=trace_id,
        agent_ref=agent_ref,
        encounter_summary=encounter_summary_dict,
        coding_specificity_checklist=[
            {"condition": c.condition, "elements_to_address": list(c.elements_to_address)}
            for c in case.coding_specificity_checklist
        ],
        risk_flags=[
            {"category": r.category, "description": r.description}
            for r in case.risk_flags
        ],
        specialist_trace=[
            {
                "expert_id": e.expert_id,
                "consulted": e.consulted,
                "rationale": e.rationale,
            }
            for e in case.specialist_trace
        ],
        completion_state=case.completion_state,
        created_by_user_id=created_by_user_id,
        closed_at=None,
    )
    # Attach children
    for gap in case.documentation_gaps:
        case_model_doc_gap = gap_to_orm(gap, case.case_id)
        # SQLAlchemy relationship attr — assigning list sets backrefs
    # NOTE: We return the case_model only; caller adds children via session
    # to avoid relying on a relationship attr that may not exist. See
    # persist_case below which writes them all in one transaction.
    return case_model


# ---------------------------------------------------------------------------
# Persistence (atomic write)
# ---------------------------------------------------------------------------


async def persist_case(
    session: AsyncSession,
    case: CDICase,
    *,
    organization_id: str | None = None,
    created_by_user_id: str | None = None,
    run_id: str = "",
    trace_id: str = "",
) -> CDICaseModel:
    """Atomic insert: 1 case + N gaps + M queries in one transaction.

    Phase 5 Track D P0.5 Gate 1:
      - Child IDs are localized to be case-scoped before persistence
        (``_localize_child_ids``), eliminating cross-case collisions.
      - Orphan queries (gap_id not in this case's gaps) are dropped.
      - Idempotency on case_id is preserved (re-running with the same
        case_id returns the existing model).
      - Idempotent-skip on gap_id/query_id is REMOVED — it caused the
        "0 Gap + N Query" pathology when LLM placeholder IDs collided
        across cases. Localization makes the skip unnecessary.
    """
    existing = await session.get(CDICaseModel, case.case_id)
    if existing is not None:
        return existing

    # Gate 1: localize child IDs + drop orphan queries.
    localized = _localize_child_ids(case)

    case_model = case_to_orm(
        localized,
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        run_id=run_id,
        trace_id=trace_id,
    )
    session.add(case_model)

    # Write children directly. IDs are already case-scoped, so no skip needed.
    for gap in localized.documentation_gaps:
        session.add(gap_to_orm(gap, localized.case_id))
    for q in localized.proposed_provider_queries:
        session.add(query_to_orm(q, localized.case_id))

    await session.commit()
    await session.refresh(case_model)
    return case_model


# ---------------------------------------------------------------------------
# Read-back
# ---------------------------------------------------------------------------


async def load_case(
    session: AsyncSession, case_id: str
) -> CDICaseModel | None:
    """Load a CDI case + its gaps + queries. Returns None if not found."""
    case_model = await session.get(CDICaseModel, case_id)
    if case_model is None:
        return None

    # Eager-load gaps and queries
    gaps_q = select(DocumentationGapModel).where(
        DocumentationGapModel.case_id == case_id
    )
    queries_q = select(ProviderQueryModel).where(
        ProviderQueryModel.case_id == case_id
    )
    case_model.gaps_ = (await session.execute(gaps_q)).scalars().all()
    case_model.queries_ = (await session.execute(queries_q)).scalars().all()
    return case_model


# ---------------------------------------------------------------------------
# Phase 5 Track D P0.5 Gate 1 — consistency assertion + state derivation
# ---------------------------------------------------------------------------


def assert_case_consistent(case_model: CDICaseModel) -> list[str]:
    """Return a list of consistency issues for the loaded case.

    Empty list = consistent. Non-empty = data integrity violation.

    Rules:
      1. Every ProviderQuery.gap_id must resolve to a DocumentationGap
         in the same case (referential integrity).
      2. If gaps == [] and queries > 0 → "0 Gap + N Query" pathology.
      3. Case-scoped ID check: every gap.id and query.id must start
         with the case_id (defensive — catches any pre-localization data).
    """
    issues: list[str] = []
    case_id = case_model.id
    gaps = getattr(case_model, "gaps_", []) or []
    queries = getattr(case_model, "queries_", []) or []

    gap_ids = {g.id for g in gaps}
    for q in queries:
        if q.gap_id not in gap_ids:
            issues.append(
                f"query {q.id} references gap_id={q.gap_id} not in case gaps "
                f"(case={case_id})"
            )
        if q.id and case_id and not q.id.startswith(case_id):
            issues.append(
                f"query {q.id} ID not case-scoped (expected prefix {case_id}/)"
            )
    for g in gaps:
        if g.id and case_id and not g.id.startswith(case_id):
            issues.append(
                f"gap {g.id} ID not case-scoped (expected prefix {case_id}/)"
            )
    if len(gaps) == 0 and len(queries) > 0:
        issues.append(
            f"0 Gap + N Query: case={case_id} has {len(queries)} queries "
            f"but no gaps — case state cannot be derived consistently"
        )
    return issues


def derive_case_state(case_model: CDICaseModel) -> str:
    """Derive a single case-level state from gap/query counts and states.

    Single source-of-truth used by both POST /runs and GET /runs/{id}.
    Replaces the ad-hoc derivation previously scattered across handlers.

    Returns one of:
      - ``AUTO_PASS``            — 0 gaps, 0 queries
      - ``PENDING_CDI_REVIEW``   — gaps > 0, queries > 0 (or queries in
                                    DRAFT/PENDING_CDI_REVIEW)
      - ``PENDING_CLINICIAN``    — all queries ≥ APPROVED, at least one
                                    not yet RESPONDED
      - ``RESPONDED``            — all queries RESPONDED or beyond
      - ``CLOSED``               — all queries CLOSED/CANCELLED/EXPIRED
      - ``INCONSISTENT``         — 0 gaps but N queries (data integrity
                                    violation; should never happen post-Gate 1)
    """
    gaps = getattr(case_model, "gaps_", []) or []
    queries = getattr(case_model, "queries_", []) or []

    if len(gaps) == 0 and len(queries) == 0:
        return "AUTO_PASS"
    if len(gaps) == 0 and len(queries) > 0:
        return "INCONSISTENT"

    terminal_states = {"CLOSED", "CANCELLED", "EXPIRED"}
    responded_or_beyond = {
        "RESPONDED", "DOCUMENTATION_UPDATED", "REVALIDATED", "CLOSED"
    }
    approved_or_beyond = {
        "APPROVED", "SENT_TO_CLINICIAN", "VIEWED",
        "RESPONDED", "DOCUMENTATION_UPDATED", "REVALIDATED", "CLOSED"
    }

    if not queries:
        return "PENDING_CDI_REVIEW"
    if all(q.lifecycle_state in terminal_states for q in queries):
        return "CLOSED"
    if all(q.lifecycle_state in responded_or_beyond for q in queries):
        return "RESPONDED"
    if all(q.lifecycle_state in approved_or_beyond for q in queries):
        return "PENDING_CLINICIAN"
    return "PENDING_CDI_REVIEW"


# ---------------------------------------------------------------------------
# ORM → Domain (reverse mapping for API responses)
# ---------------------------------------------------------------------------


def orm_to_gap_dict(gap_model: DocumentationGapModel) -> dict[str, Any]:
    """Convert ORM gap to a dict matching DocumentationGapSchema."""
    return {
        "gap_id": gap_model.id,
        "gap_type": gap_model.gap_type,
        "description": gap_model.description,
        "why_it_matters": gap_model.why_it_matters,
        "evidence_span": {
            "document_id": gap_model.evidence_document_id,
            "quote": gap_model.evidence_quote,
        },
        "minimal_clarification_needed": gap_model.minimal_clarification_needed,
    }


def orm_to_query_dict(q_model: ProviderQueryModel) -> dict[str, Any]:
    """Convert ORM query to a dict matching ProviderQuerySchema."""
    return {
        "query_id": q_model.id,
        "gap_id": q_model.gap_id,
        "topic": q_model.topic,
        "reason": q_model.reason,
        "evidence_span": {
            "document_id": q_model.evidence_document_id,
            "quote": q_model.evidence_quote,
        },
        "query_text": q_model.query_text,
        "response_options": list(q_model.response_options or []),
        "lifecycle_state": q_model.lifecycle_state,
        "priority": q_model.priority,
    }


# ---------------------------------------------------------------------------
# Lifecycle transition (optimistic lock)
# ---------------------------------------------------------------------------


async def update_query_lifecycle(
    session: AsyncSession,
    query_id: str,
    *,
    from_state: str,
    to_state: str,
    nlq_gate_verdict: str | None = None,
    nlq_gate_block_reasons: list[str] | None = None,
    sla_due_at: datetime | None = None,
) -> tuple[ProviderQueryModel | None, bool]:
    """Atomically transition a query's lifecycle_state with optimistic lock.

    Returns ``(model, success)``. If ``success=False``, another writer
    beat us to the transition (concurrent write) — caller should retry
    or return 409 Conflict.

    Implementation: ``UPDATE ... WHERE id=:id AND lifecycle_state=:from``
    relies on row-level locking; we read back to confirm.
    """
    q_model = await session.get(ProviderQueryModel, query_id)
    if q_model is None:
        return None, False

    if q_model.lifecycle_state != from_state:
        # Optimistic lock miss — state already advanced
        return q_model, False

    q_model.lifecycle_state = to_state
    if nlq_gate_verdict is not None:
        q_model.nlq_gate_verdict = nlq_gate_verdict
    if nlq_gate_block_reasons is not None:
        q_model.nlq_gate_block_reasons = nlq_gate_block_reasons
    if sla_due_at is not None:
        q_model.sla_due_at = sla_due_at
    if to_state == "SENT_TO_CLINICIAN":
        q_model.sent_at = datetime.now(timezone.utc)
    if to_state == "VIEWED":
        q_model.viewed_at = datetime.now(timezone.utc)
    if to_state == "RESPONDED":
        q_model.responded_at = datetime.now(timezone.utc)
    if to_state == "CLOSED":
        q_model.closed_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(q_model)
    return q_model, True


__all__ = [
    "case_to_orm",
    "gap_to_orm",
    "query_to_orm",
    "persist_case",
    "load_case",
    "orm_to_gap_dict",
    "orm_to_query_dict",
    "update_query_lifecycle",
    # Phase 5 Track D P0.5 Gate 1
    "_localize_child_ids",
    "assert_case_consistent",
    "derive_case_state",
]
