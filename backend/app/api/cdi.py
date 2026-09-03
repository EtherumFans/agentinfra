"""CDI Core Entry Agent REST API (Phase 5 Track D Gate 9).

Exposes the CDI orchestrator + clarification lifecycle as HTTP endpoints
so the frontend workbench (`/ai-studio/cdi`) can drive the full clinical
documentation improvement workflow.

PDF §13 Gate 9 reference:
    reports/phase5_track_d/GATE9_API_A2A_HOSPITAL_INTEGRATION_REPORT.md

Endpoints (all under `/api/v1/cdi`):

    POST /runs                          Run CDI orchestrator on chart text
    GET  /runs/{case_id}                Fetch case state
    POST /queries/{query_id}/transition Drive lifecycle transition
    GET  /audit/dashboard               Build audit dashboard snapshot
    POST /subscriptions                 Register notification subscription

Boundary: this router does NOT call medical-coding tools. CDI ≠ coding.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.icoder.agent_runtime.cdi import (
    CDICase,
    CDIOrchestrator,
    EvidenceSpan,
    RealCDIRunner,
    stub_runner,
)
from app.icoder.agent_runtime.orchestrator.phi_redactor import PHIRedactor
from app.config import settings
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.models.cdi_case import CDINotificationSubscriptionModel
from app.database import get_db
from app.services.cdi_persistence import (
    assert_case_consistent,
    derive_case_state,
    load_case as load_case_persisted,
    orm_to_gap_dict,
    orm_to_query_dict,
    persist_case as persist_case_to_db,
    update_query_lifecycle,
)
from app.services.cdi_query_lifecycle import (
    LifecycleState,
    compute_sla_due_at,
    gate_draft_to_pending_review,
)
from app.services.phi_encryption import encrypt_phi, is_encryption_enabled
from app.services.system_audit import tenant_owned_system_audit
from app.services.cdi_roles_notifications import (
    AuditDashboardSnapshot,
    CdiRole,
    NotificationSubscription,
    NotificationEvent,
    SLABreachRecord,
    build_audit_dashboard,
    can_drive_transition,
    find_sla_breaches,
    platform_role_to_cdi_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cdi", tags=["cdi"])

_QUERY_AUDIT_PLATFORM_ROLES = {
    "admin",
    "qc",
    "insurance",
    "dept_head",
    "coder",
    "it",
}


def _project_query_audit_queue(
    queue: list[dict[str, Any]],
    current_user: User,
) -> list[dict[str, Any]]:
    """Fail closed for clinician and unknown roles at the API boundary."""
    raw_role = getattr(current_user, "role", "")
    platform_role = raw_role.value if hasattr(raw_role, "value") else str(raw_role)
    if platform_role not in _QUERY_AUDIT_PLATFORM_ROLES:
        return []
    return list(queue)


def _pseudonymize_reference(value: str, *, kind: str, tenant_id: str) -> str:
    """Return a stable tenant-scoped pseudonym without persisting raw IDs."""
    normalized = (value or "").strip()
    if not normalized:
        return "DEID"
    key = hashlib.sha256(
        f"icoder:cdi-reference:v1:{settings.SECRET_KEY}".encode("utf-8")
    ).digest()
    digest = hmac.new(
        key,
        f"{tenant_id}:{kind}:{normalized}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    return f"PSEUDO-{kind.upper()}-{digest}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CDIRunRequest(BaseModel):
    """Request body for POST /api/v1/cdi/runs."""

    chart_excerpt: str = Field(
        ..., min_length=1, max_length=32000,
        description="Raw chart text (admission note, progress note, etc).",
    )
    case_id: str | None = Field(
        default=None,
        pattern=r"^CASE-[A-Za-z0-9_-]{1,48}$",
        description="Optional non-PHI case ID. Auto-generated UUID if omitted.",
    )
    patient_ref: str = Field(default="", description="Patient reference (MRN or deidentified ID)")
    encounter_ref: str = Field(default="", description="Encounter reference (visit ID)")

    model_config = {"json_schema_extra": {"example": {
        "chart_excerpt": "患者男性,58岁,因'咳嗽咳痰伴发热 3 天'入院。查体:T 38.5℃...",
        "case_id": "CASE-2026-07-11-001",
        "patient_ref": "MRN-DEID-001",
        "encounter_ref": "ENC-001",
    }}}


class EvidenceSpanSchema(BaseModel):
    document_id: str = ""
    quote: str = ""
    char_start: int = 0
    char_end: int = 0
    documented_at: str = ""


class DocumentationGapSchema(BaseModel):
    gap_id: str
    gap_type: str
    description: str
    why_it_matters: str = ""
    evidence_span: EvidenceSpanSchema | None = None
    minimal_clarification_needed: str = ""


class ProviderQuerySchema(BaseModel):
    query_id: str
    gap_id: str
    topic: str
    reason: str = ""
    evidence_span: EvidenceSpanSchema | None = None
    evidence_spans: list[EvidenceSpanSchema] = Field(default_factory=list)
    query_text: str
    response_options: list[str] = []
    lifecycle_state: str = "DRAFT"
    priority: str = "routine"
    nlq_gate_verdict: str = "PENDING"
    nlq_gate_block_reasons: list[str] = Field(default_factory=list)


class StageTraceSchema(BaseModel):
    """Per-stage provider/model/latency/token evidence (PDF §A2).

    Surfaced on every CDI run so the audit log and Specialist Trace
    panel can prove the LLM was actually invoked — not stubbed.
    """

    stage: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    run_id: str = ""
    trace_id: str = ""
    degraded: bool = False
    error_reason: str = ""
    expert_id: str = ""


class CDIRunResponse(BaseModel):
    """Response for POST /api/v1/cdi/runs."""

    case_id: str
    completion_state: str
    documentation_gaps: list[DocumentationGapSchema]
    proposed_provider_queries: list[ProviderQuerySchema]
    query_rewrite_queue: list[dict[str, Any]] = Field(default_factory=list)
    chart_excerpt_preview: str
    patient_ref: str = "DEID"
    encounter_ref: str = "DEID"
    encounter_summary: dict[str, Any] | None = None
    risk_flags: list[dict[str, str]] = []
    specialist_trace: list[dict[str, Any]] = []
    stage_run_ids: dict[str, str] = {}
    stage_trace_ids: dict[str, str] = {}
    # Phase 5 Track D P0 Gate 2: per-stage provider evidence (PDF §A2).
    stage_traces: list[StageTraceSchema] = []
    # True when any stage had to fall back to empty outputs due to LLM
    # provider failure. Front-end surfaces a warning banner.
    degraded: bool = False
    runtime_mode: str = "real"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TransitionRequest(BaseModel):
    """Drive a lifecycle transition on a Provider Query."""

    to_state: str = Field(..., description="Target lifecycle state")
    role_hint: str | None = Field(
        default=None,
        description="Override CDI role (default: derive from user role).",
    )
    # For DRAFT → PENDING_CDI_REVIEW gate
    query_text: str | None = None
    response_options: list[str] | None = None
    evidence_quote: str | None = None
    topic: str | None = None
    priority: str = "routine"


class TransitionResponse(BaseModel):
    query_id: str
    accepted: bool
    from_state: str
    to_state: str
    reason: str = ""
    sla_due_at: datetime | None = None
    nlq_gate_passed: bool | None = None
    rbac_allowed: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditDashboardResponse(BaseModel):
    """Tenant-scoped CDI workflow metrics for auditor/admin roles."""

    generated_at: str
    total_cases: int = Field(..., ge=0)
    total_queries: int = Field(..., ge=0)
    queries_by_state: dict[str, int]
    queries_by_priority: dict[str, int]
    breaches_critical: int = Field(..., ge=0)
    breaches_warning: int = Field(..., ge=0)
    response_category_distribution: dict[str, int]
    average_hours_to_response: float | None = None
    average_hours_to_close: float | None = None
    top_gap_types: list[tuple[str, int]]
    escalation_rate: float = Field(..., ge=0.0, le=1.0)
    note: str


class SubscriptionRequest(BaseModel):
    """Register a notification subscription."""

    user_role: str
    events: list[str]
    channel: str = "in_app"
    target_url: str = ""
    secret: str = ""


class SubscriptionResponse(BaseModel):
    subscription_id: str
    user_role: str
    events: list[str]
    channel: str
    target_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# POST /runs — run the CDI orchestrator
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=CDIRunResponse)
async def run_cdi(
    body: CDIRunRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> CDIRunResponse:
    """Run the CDI orchestrator against chart_excerpt.

    Returns the case state including documentation_gaps and
    proposed_provider_queries. Each query starts in DRAFT state.

    Phase 5 Track D P0 Gate 2 (2026-07-11): wires the real DeepSeek-backed
    runner. ``stub_runner`` is retained ONLY for unit tests. Each stage's
    run_id / trace_id / provider / model / latency / tokens are surfaced
    via ``stage_traces`` for audit evidence (PDF §A1 + §A2).

    Phase 5 Track D P0 Gate 3 (2026-07-11): persists case + gaps + queries
    atomically (PDF §A3). Idempotent on case_id. GET /runs/{case_id} now
    reads back the persisted state instead of returning 501.

    Boundary: this endpoint does NOT call medical-coding tools.
    CDI produces clarification queries; coding happens in a separate
    Medical Coding Agent run AFTER documentation is clarified.
    """

    case_id = body.case_id or f"CASE-{uuid.uuid4().hex[:12]}"
    organization_id = str(current_org.id)
    tenant_id = organization_id
    redaction = PHIRedactor().redact(body.chart_excerpt)
    safe_chart_excerpt = redaction.redacted_text
    safe_patient_ref = _pseudonymize_reference(
        body.patient_ref, kind="patient", tenant_id=tenant_id,
    )
    safe_encounter_ref = _pseudonymize_reference(
        body.encounter_ref, kind="encounter", tenant_id=tenant_id,
    )

    case = CDICase(
        case_id=case_id,
        chart_excerpt=safe_chart_excerpt,
        patient_ref=safe_patient_ref,
        encounter_ref=safe_encounter_ref,
    )

    # Gate 2: real DeepSeek-backed runner. Falls back to stub_runner ONLY
    # in unit-test mode (env-driven) to keep the 18 Gate 3 tests intact.
    use_stub = (
        os.environ.get("ICODER_CDI_FORCE_STUB_FOR_TESTS") == "1"
        and "pytest" in sys.modules
    )
    if not use_stub and str(settings.LLM_PROVIDER or "").lower() == "mock":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "provider_unavailable",
                "message": "CDI LLM provider is unavailable; no clinical result was produced.",
                "manual_review_required": True,
            },
        )
    if use_stub:
        runner = stub_runner
        stage_traces_dict: dict[str, Any] = {}
        expert_traces_list: list[Any] = []
    else:
        runner_instance = RealCDIRunner()
        runner = runner_instance
        stage_traces_dict = runner_instance.stage_traces
        expert_traces_list = runner_instance.expert_traces

    orchestrator = CDIOrchestrator(runner=runner)
    # Run the sync orchestrator in a worker thread. One request-scoped event
    # loop and LLM client are shared across every CDI stage, then explicitly
    # closed before returning; async HTTP pools must never cross event loops.
    case = await asyncio.to_thread(orchestrator.run, case)

    degraded_safety_gates = dict(case.degraded_safety_gates)
    if not use_stub and (
        degraded_safety_gates
        or any(
        trace.degraded
        for trace in list(stage_traces_dict.values()) + list(expert_traces_list)
        )
    ):
        try:
            await tenant_owned_system_audit(
                db,
                organization_id=organization_id,
                action="cdi.run.failed.required_gate_degraded",
                resource_type="cdi_case",
                resource_id=case_id,
                details={
                    "degraded_safety_gates": degraded_safety_gates,
                    "manual_review_required": True,
                    "clinical_result_published": False,
                },
                status="failure",
                error_message="required CDI safety gate degraded",
                user_id=str(current_user.id),
            )
            await db.commit()
        except Exception as audit_error:
            await db.rollback()
            logger.error(
                "CDI required-gate failure audit could not be persisted "
                "error_type=%s",
                type(audit_error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "audit_persistence_failed",
                    "message": "CDI failure was not published because its audit record could not be persisted.",
                    "manual_review_required": True,
                },
            ) from None
        raise HTTPException(
            status_code=503,
            detail={
                "error": "provider_execution_failed",
                "message": "CDI execution degraded; no clinical result was published.",
                "manual_review_required": True,
                "degraded_safety_gates": sorted(degraded_safety_gates),
            },
        )

    # Gate 3: persist case + gaps + queries atomically (PDF §A3).
    # Idempotent on case_id — existing rows short-circuit.
    run_id_for_persist = (
        case.stage_run_ids.get("specialist_trace_emit")
        or case.stage_run_ids.get("encounter_synthesis")
        or ""
    )
    trace_id_for_persist = (
        case.stage_trace_ids.get("specialist_trace_emit")
        or case.stage_trace_ids.get("encounter_synthesis")
        or ""
    )

    # Phase 5 Track D P0.5 Gate 1 — localize child IDs BEFORE persistence
    # AND before building the response, so the in-memory case, the DB
    # rows, and the API response all use the same case-scoped IDs.
    from app.services.cdi_persistence import _localize_child_ids
    case = _localize_child_ids(case)

    try:
        await persist_case_to_db(
            db,
            case,
            organization_id=organization_id,
            created_by_user_id=current_user.id,
            run_id=run_id_for_persist,
            trace_id=trace_id_for_persist,
        )
    except Exception as e:
        # Persistence failure is non-fatal — the run still produced
        # results. Log + continue so the user sees their answer.
        logger.error(
            "CDI case persistence failed error_type=%s", type(e).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "audit_persistence_failed",
                "message": "CDI result was not published because audit persistence failed.",
                "manual_review_required": True,
            },
        ) from None

    gaps = [
        DocumentationGapSchema(
            gap_id=g.gap_id,
            gap_type=g.gap_type,
            description=g.description,
            why_it_matters=g.why_it_matters,
            evidence_span=EvidenceSpanSchema(
                document_id=g.evidence_span.document_id,
                quote=g.evidence_span.quote,
            ) if g.evidence_span else None,
            minimal_clarification_needed=g.minimal_clarification_needed,
        )
        for g in case.documentation_gaps
    ]

    queries = [
        ProviderQuerySchema(
            query_id=q.query_id,
            gap_id=q.gap_id,
            topic=q.topic,
            reason=q.reason,
            evidence_span=EvidenceSpanSchema(
                document_id=q.evidence_span.document_id,
                quote=q.evidence_span.quote,
                char_start=q.evidence_span.char_start,
                char_end=q.evidence_span.char_end,
                documented_at=q.evidence_span.documented_at,
            ) if q.evidence_span else None,
            evidence_spans=[
                EvidenceSpanSchema(
                    document_id=span.document_id,
                    quote=span.quote,
                    char_start=span.char_start,
                    char_end=span.char_end,
                    documented_at=span.documented_at,
                )
                for span in q.all_evidence_spans()
            ],
            query_text=q.query_text,
            response_options=q.response_options,
            lifecycle_state=q.lifecycle_state,
            priority=q.priority,
            nlq_gate_verdict=q.nlq_gate_verdict or "PENDING",
            nlq_gate_block_reasons=list(q.nlq_gate_block_reasons),
        )
        for q in case.proposed_provider_queries
    ]

    # Flatten stage_traces + expert_traces for the response payload.
    trace_records: list[StageTraceSchema] = []
    degraded = False
    for st in list(stage_traces_dict.values()) + list(expert_traces_list):
        trace_records.append(StageTraceSchema(
            stage=st.stage,
            provider=st.provider,
            model=st.model,
            latency_ms=st.latency_ms,
            prompt_tokens=st.prompt_tokens,
            completion_tokens=st.completion_tokens,
            total_tokens=st.total_tokens,
            run_id=st.run_id,
            trace_id=st.trace_id,
            degraded=st.degraded,
            error_reason=st.error_reason,
            expert_id=st.expert_id,
        ))
        if st.degraded:
            degraded = True

    return CDIRunResponse(
        case_id=case.case_id,
        completion_state=case.completion_state,
        documentation_gaps=gaps,
        proposed_provider_queries=queries,
        query_rewrite_queue=_project_query_audit_queue(
            list(case.query_rewrite_queue), current_user,
        ),
        chart_excerpt_preview=safe_chart_excerpt[:200],
        patient_ref=case.patient_ref or "DEID",
        encounter_ref=case.encounter_ref or "DEID",
        encounter_summary=(
            {
                "key_points": list(case.encounter_summary.key_points),
                "encounter_metadata": dict(case.encounter_summary.encounter_metadata),
            }
            if case.encounter_summary is not None
            else None
        ),
        risk_flags=[
            {"category": r.category, "description": r.description}
            for r in case.risk_flags
        ],
        specialist_trace=[
            {
                "expert_id": e.expert_id,
                "consulted": e.consulted,
                "rationale": e.rationale,
                # Phase 5 Track D P0.5 Gate 5 — Conditional Expert Routing.
                # route_decision is the front-end label ("needed" /
                # "not_needed" / "missing_inputs" / "tool_unavailable").
                # execution_mode is the audit-grade enum. route_reason
                # is the human-readable rationale.
                "route_decision": getattr(e, "route_decision", ""),
                "route_reason": getattr(e, "route_reason", ""),
                "execution_mode": getattr(e, "execution_mode", ""),
                "latency_ms": getattr(e, "latency_ms", 0),
                "tokens": getattr(e, "tokens", 0),
            }
            for e in case.specialist_trace
        ],
        stage_run_ids=case.stage_run_ids,
        stage_trace_ids=case.stage_trace_ids,
        stage_traces=trace_records,
        degraded=degraded,
        runtime_mode="stub" if use_stub else "real",
    )


# ---------------------------------------------------------------------------
# GET /runs/{case_id} — fetch persisted case state (Gate 3 real read)
# ---------------------------------------------------------------------------


@router.get("/runs/{case_id:path}")
async def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch a CDI case by ID.

    Phase 5 Track D P0 Gate 3 (2026-07-11): real read-back from the
    ``cdi_cases`` table (PDF §A3 — closed loop). Returns 404 if the case
    has never been persisted (e.g. an in-memory-only run from before
    Gate 3, or a typo'd case_id).
    """
    organization_id = str(current_org.id)
    case_model = await load_case_persisted(
        db, case_id, organization_id=organization_id,
    )
    if case_model is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "case_not_found",
                "message": f"No persisted CDI case with id='{case_id}'",
                "case_id": case_id,
            },
        )
    # Phase 5 Track D P0.5 Gate 1 — consistency assertion on read-back.
    consistency_issues = assert_case_consistent(case_model)
    if consistency_issues:
        # Surface the diagnostic but do not 500 — the API contract returns
        # the case as persisted. Frontend will show the inconsistent state
        # and the diagnostic so the operator can run the repair script.
        logger.warning("cdi.get_case.consistency case=%s issues=%s", case_id, consistency_issues)

    gaps = [orm_to_gap_dict(g) for g in getattr(case_model, "gaps_", [])]
    queries = [orm_to_query_dict(q) for q in getattr(case_model, "queries_", [])]
    derived_state = derive_case_state(case_model)
    return {
        "case_id": case_model.id,
        "completion_state": derived_state if derived_state != "INCONSISTENT" else case_model.completion_state,
        "derived_case_state": derived_state,
        "consistency_issues": consistency_issues,
        "patient_ref": case_model.patient_ref,
        "encounter_ref": case_model.encounter_ref,
        "chart_excerpt_preview": f"(persisted case, length={case_model.chart_excerpt_length})",
        "chart_excerpt_length": case_model.chart_excerpt_length,
        "encounter_summary": case_model.encounter_summary or None,
        "documentation_gaps": gaps,
        "proposed_provider_queries": queries,
        "query_rewrite_queue": _project_query_audit_queue(
            list(case_model.query_rewrite_queue or []), current_user,
        ),
        "risk_flags": list(case_model.risk_flags or []),
        "specialist_trace": list(case_model.specialist_trace or []),
        "stage_run_ids": {},
        "stage_trace_ids": {},
        "stage_traces": [],
        "degraded": False,
        "runtime_mode": "persisted",
        "run_id": case_model.run_id,
        "trace_id": case_model.trace_id,
        "agent_ref": case_model.agent_ref,
        "created_at": case_model.created_at.isoformat() if case_model.created_at else None,
        "closed_at": case_model.closed_at.isoformat() if case_model.closed_at else None,
    }


# ---------------------------------------------------------------------------
# POST /queries/{query_id}/transition — drive lifecycle
# ---------------------------------------------------------------------------


@router.post("/queries/{query_id:path}/transition", response_model=TransitionResponse)
async def transition_query(
    query_id: str,
    body: TransitionRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TransitionResponse:
    """Drive a lifecycle transition on a Provider Query.

    Enforces (Phase 5 Track D P0.5 Gate 7):
      1. Query exists (404 if not).
      2. RBAC: CDI role must be allowed to drive this (from_state, to_state).
      3. NLQ gate: DRAFT → PENDING_CDI_REVIEW requires query to pass
         non-leading query rules (NLQ-001..011).
      4. Optimistic-lock DB write via ``update_query_lifecycle`` (409 on conflict).

    Returns the transition result. State is persisted before return —
    GET /runs/{case_id} will reflect the new lifecycle_state immediately.
    """

    from app.models.cdi_case import CDICaseModel, ProviderQueryModel

    # 0. Fetch current row to get real from_state
    organization_id = str(current_org.id)
    q_model = (
        await db.execute(
            select(ProviderQueryModel)
            .join(CDICaseModel, ProviderQueryModel.case_id == CDICaseModel.id)
            .where(
                ProviderQueryModel.id == query_id,
                CDICaseModel.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if q_model is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "query_not_found",
                "query_id": query_id,
            },
        )
    real_from_state: str = q_model.lifecycle_state

    # 1. RBAC check — CDI role derived from platform role (or role_hint override)
    platform_role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    cdi_role: CdiRole = (
        body.role_hint  # type: ignore[assignment]
        if body.role_hint in ("cdi_specialist", "clinician", "auditor", "admin")
        else platform_role_to_cdi_role(platform_role)
    )

    rbac = can_drive_transition(cdi_role, real_from_state, body.to_state)
    if not rbac.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "cdi_role": cdi_role,
                "from_state": real_from_state,
                "to_state": body.to_state,
                "reason": rbac.reason,
            },
        )

    # 2. NLQ gate (DRAFT → PENDING_CDI_REVIEW only)
    nlq_passed: bool | None = None
    nlq_block_reasons: list[str] = []
    if body.to_state == "PENDING_CDI_REVIEW":
        if not all(
            [body.query_text, body.response_options, body.evidence_quote, body.topic]
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "nlq_gate_input_required",
                    "message": (
                        "DRAFT → PENDING_CDI_REVIEW requires query_text, "
                        "response_options, evidence_quote, topic."
                    ),
                },
            )
        gate_result = gate_draft_to_pending_review(
            query_text=body.query_text or "",
            response_options=body.response_options or [],
            evidence_quote=body.evidence_quote or "",
            topic=body.topic or "",
        )
        nlq_passed = gate_result.verdict == "PASS"
        nlq_block_reasons = list(gate_result.rules_failed)
        if not nlq_passed:
            # Persist the BLOCK verdict so audit dashboard sees it
            await update_query_lifecycle(
                db,
                query_id,
                from_state=real_from_state,
                to_state=real_from_state,  # no state change
                nlq_gate_verdict="BLOCK",
                nlq_gate_block_reasons=nlq_block_reasons,
                organization_id=organization_id,
            )
            return TransitionResponse(
                query_id=query_id,
                accepted=False,
                from_state=real_from_state,
                to_state=body.to_state,
                reason=f"NLQ gate failed: {len(nlq_block_reasons)} rules",
                nlq_gate_passed=False,
                rbac_allowed=True,
            )

    # 3. SLA computation on APPROVED
    sla_due_at: datetime | None = None
    if body.to_state == "APPROVED":
        sla_due_at = compute_sla_due_at(
            datetime.now(timezone.utc), body.priority  # type: ignore[arg-type]
        )

    # 4. Optimistic-lock DB write
    nlq_verdict_str = "PASS" if nlq_passed else None
    updated_model, success = await update_query_lifecycle(
        db,
        query_id,
        from_state=real_from_state,
        to_state=body.to_state,
        nlq_gate_verdict=nlq_verdict_str,
        nlq_gate_block_reasons=nlq_block_reasons or None,
        sla_due_at=sla_due_at,
        organization_id=organization_id,
    )

    if not success:
        # Optimistic lock miss — another writer moved state first
        current_state = updated_model.lifecycle_state if updated_model else real_from_state
        raise HTTPException(
            status_code=409,
            detail={
                "error": "concurrent_transition",
                "query_id": query_id,
                "expected_from": real_from_state,
                "current_state": current_state,
            },
        )

    return TransitionResponse(
        query_id=query_id,
        accepted=True,
        from_state=real_from_state,
        to_state=body.to_state,
        reason="ok",
        sla_due_at=sla_due_at,
        nlq_gate_passed=nlq_passed,
        rbac_allowed=True,
    )


# ---------------------------------------------------------------------------
# GET /audit/dashboard — auditor's overview
# ---------------------------------------------------------------------------


@router.get("/audit/dashboard", response_model=AuditDashboardResponse)
async def get_audit_dashboard(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AuditDashboardResponse:
    """Build the audit dashboard snapshot.

    Persisted cases, gaps, queries and clinician responses are aggregated only
    inside the authenticated organization. Raw chart and response text are not
    returned by this endpoint.
    """

    platform_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    cdi_role = platform_role_to_cdi_role(platform_role)

    if cdi_role not in ("auditor", "admin"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "Audit dashboard is only available to auditor/admin roles.",
                "user_cdi_role": cdi_role,
            },
        )

    # Read only tenant-linked rows; no raw chart content is selected.
    from app.models.cdi_case import (
        CDICaseModel,
        ClinicianResponseModel,
        DocumentationGapModel,
        ProviderQueryModel,
    )

    organization_id = str(current_org.id)
    case_rows = (
        await db.execute(
            select(CDICaseModel).where(
                CDICaseModel.organization_id == organization_id,
            )
        )
    ).scalars().all()
    query_rows = (
        await db.execute(
            select(ProviderQueryModel, DocumentationGapModel.gap_type)
            .join(CDICaseModel, ProviderQueryModel.case_id == CDICaseModel.id)
            .join(
                DocumentationGapModel,
                ProviderQueryModel.gap_id == DocumentationGapModel.id,
            )
            .where(CDICaseModel.organization_id == organization_id)
        )
    ).all()
    response_rows = (
        await db.execute(
            select(ClinicianResponseModel)
            .join(CDICaseModel, ClinicianResponseModel.case_id == CDICaseModel.id)
            .where(CDICaseModel.organization_id == organization_id)
        )
    ).scalars().all()

    cases = [
        {"case_id": row.id, "created_at": row.created_at}
        for row in case_rows
    ]
    queries = [
        {
            "query_id": row.id,
            "case_id": row.case_id,
            "lifecycle_state": row.lifecycle_state,
            "priority": row.priority,
            "gap_type": gap_type,
            "created_at": row.created_at,
            "approved_at": (
                row.sent_at or row.created_at
                if row.lifecycle_state not in {"DRAFT", "PENDING_CDI_REVIEW"}
                else None
            ),
            "closed_at": row.closed_at,
        }
        for row, gap_type in query_rows
    ]
    responses = [
        {
            "query_id": row.query_id,
            "category": str(
                (row.response_metadata or {}).get("category") or "unknown"
            ),
            "submitted_at": row.submitted_at,
        }
        for row in response_rows
    ]
    snap = build_audit_dashboard(cases, queries, responses)
    return AuditDashboardResponse(**{
        "generated_at": snap.generated_at.isoformat(),
        "total_cases": snap.total_cases,
        "total_queries": snap.total_queries,
        "queries_by_state": snap.queries_by_state,
        "queries_by_priority": snap.queries_by_priority,
        "breaches_critical": snap.breaches_critical,
        "breaches_warning": snap.breaches_warning,
        "response_category_distribution": snap.response_category_distribution,
        "average_hours_to_response": snap.average_hours_to_response,
        "average_hours_to_close": snap.average_hours_to_close,
        "top_gap_types": snap.top_gap_types,
        "escalation_rate": snap.escalation_rate,
        "note": "Tenant-scoped CDI workflow metrics from persisted records.",
    })


# ---------------------------------------------------------------------------
# POST /subscriptions — register notification subscription
# ---------------------------------------------------------------------------


@router.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    body: SubscriptionRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Register a durable, tenant-scoped notification subscription."""

    valid_events = {
        "QUERY_SENT_TO_CLINICIAN", "QUERY_VIEWED_BY_CLINICIAN",
        "QUERY_RESPONDED", "QUERY_ESCALATED", "QUERY_CLOSED",
        "SLA_BREACH_WARNING", "SLA_BREACH_CRITICAL",
    }
    requested_events = list(dict.fromkeys(body.events))
    invalid_events = set(requested_events) - valid_events
    if invalid_events:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_events",
                "invalid": list(invalid_events),
                "valid": sorted(valid_events),
            },
        )

    if not requested_events:
        raise HTTPException(
            status_code=422,
            detail={"error": "events_required"},
        )

    valid_channels = {"in_app", "webhook"}
    if body.channel not in valid_channels:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "channel_unavailable",
                "available": sorted(valid_channels),
            },
        )

    platform_role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    actor_cdi_role = platform_role_to_cdi_role(platform_role)
    valid_roles = {"cdi_specialist", "clinician", "auditor", "admin"}
    if body.user_role not in valid_roles:
        raise HTTPException(status_code=422, detail={"error": "invalid_cdi_role"})
    if actor_cdi_role != "admin" and body.user_role != actor_cdi_role:
        raise HTTPException(status_code=403, detail={"error": "role_scope_forbidden"})

    secret_encrypted = ""
    target_url = body.target_url.strip()
    if body.channel == "webhook":
        if not target_url:
            raise HTTPException(
                status_code=422,
                detail={"error": "webhook_requires_url"},
            )
        parsed = urlsplit(target_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(
                status_code=422,
                detail={"error": "webhook_requires_https_url"},
            )
        if len(body.secret) < 16:
            raise HTTPException(
                status_code=422,
                detail={"error": "webhook_secret_too_short", "minimum_length": 16},
            )
        if not is_encryption_enabled():
            raise HTTPException(
                status_code=503,
                detail={"error": "webhook_encryption_unavailable"},
            )
        try:
            secret_encrypted = encrypt_phi(body.secret) or ""
        except Exception as exc:
            logger.error(
                "CDI webhook secret encryption failed error_type=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail={"error": "webhook_encryption_failed"},
            ) from None
    else:
        target_url = ""

    sub_id = f"sub-{uuid.uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc)
    row = CDINotificationSubscriptionModel(
        id=sub_id,
        organization_id=str(current_org.id),
        created_by_user_id=str(getattr(current_user, "id", None) or "") or None,
        user_role=body.user_role,
        events=requested_events,
        channel=body.channel,
        target_url=target_url,
        secret_encrypted=secret_encrypted,
        active=True,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        db.add(row)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "CDI subscription persistence failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "subscription_persistence_failed"},
        ) from None
    return SubscriptionResponse(
        subscription_id=sub_id,
        user_role=body.user_role,
        events=requested_events,
        channel=body.channel,
        target_url=target_url,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health")
async def cdi_health() -> dict:
    """CDI router health check."""

    llm_ready = str(settings.LLM_PROVIDER or "").lower() != "mock"
    return {
        "status": "healthy" if llm_ready else "degraded",
        "router": "cdi",
        "prefix": "/api/v1/cdi",
        "endpoints": [
            "POST /runs",
            "GET /runs/{case_id}",
            "POST /queries/{query_id}/transition",
            "GET /audit/dashboard",
            "POST /subscriptions",
            "GET /health",
        ],
        "gate": "Phase 5 Track D Gate 9",
        "capabilities": {
            "clinical_runtime": "configured" if llm_ready else "unavailable_mock_provider",
            "subscription_persistence": "ready",
            "webhook_secret_encryption": (
                "ready" if is_encryption_enabled() else "configuration_required"
            ),
        },
        "boundaries_enforced": [
            "no_medical_coding_calls",
            "no_chart_modification",
            "nlq_gate_on_draft_to_pending_review",
            "rbac_per_role",
        ],
    }
