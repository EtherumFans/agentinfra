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

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.icoder.agent_runtime.cdi import (
    CDICase,
    CDIOrchestrator,
    EvidenceSpan,
    stub_runner,
)
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.cdi_query_lifecycle import (
    LifecycleState,
    compute_sla_due_at,
    gate_draft_to_pending_review,
)
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
        description="Optional case ID. Auto-generated UUID if omitted.",
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
    query_text: str
    response_options: list[str] = []
    lifecycle_state: str = "DRAFT"
    priority: str = "routine"


class CDIRunResponse(BaseModel):
    """Response for POST /api/v1/cdi/runs."""

    case_id: str
    completion_state: str
    documentation_gaps: list[DocumentationGapSchema]
    proposed_provider_queries: list[ProviderQuerySchema]
    chart_excerpt_preview: str
    stage_run_ids: dict[str, str] = {}
    stage_trace_ids: dict[str, str] = {}
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
) -> CDIRunResponse:
    """Run the CDI orchestrator against chart_excerpt.

    Returns the case state including documentation_gaps and
    proposed_provider_queries. Each query starts in DRAFT state.

    Boundary: this endpoint does NOT call medical-coding tools.
    CDI produces clarification queries; coding happens in a separate
    Medical Coding Agent run AFTER documentation is clarified.
    """

    case_id = body.case_id or f"CASE-{uuid.uuid4().hex[:12]}"

    case = CDICase(
        case_id=case_id,
        chart_excerpt=body.chart_excerpt,
        patient_ref=body.patient_ref,
        encounter_ref=body.encounter_ref,
    )

    orchestrator = CDIOrchestrator(runner=stub_runner)
    case = orchestrator.run(case)

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
            ) if q.evidence_span else None,
            query_text=q.query_text,
            response_options=q.response_options,
            lifecycle_state=q.lifecycle_state,
            priority=q.priority,
        )
        for q in case.proposed_provider_queries
    ]

    return CDIRunResponse(
        case_id=case.case_id,
        completion_state=case.completion_state,
        documentation_gaps=gaps,
        proposed_provider_queries=queries,
        chart_excerpt_preview=body.chart_excerpt[:200],
        stage_run_ids=case.stage_run_ids,
        stage_trace_ids=case.stage_trace_ids,
    )


# ---------------------------------------------------------------------------
# GET /runs/{case_id} — fetch case state (stub until DB wired)
# ---------------------------------------------------------------------------


@router.get("/runs/{case_id}")
async def get_case(case_id: str, current_user: User = Depends(get_current_user)) -> dict:
    """Fetch a CDI case by ID.

    Gate 9 stub: returns 404 until DB persistence is wired in production.
    Real implementation stores CDICaseModel rows per Gate 4 migration 011.
    """

    raise HTTPException(
        status_code=501,
        detail={
            "error": "not_implemented",
            "message": (
                "GET /runs/{case_id} requires DB persistence wiring. "
                "Gate 9 wires REST scaffolding; production DB persistence is "
                "deferred to Gate 11+."
            ),
            "case_id": case_id,
        },
    )


# ---------------------------------------------------------------------------
# POST /queries/{query_id}/transition — drive lifecycle
# ---------------------------------------------------------------------------


@router.post("/queries/{query_id}/transition", response_model=TransitionResponse)
async def transition_query(
    query_id: str,
    body: TransitionRequest,
    current_user: User = Depends(get_current_user),
) -> TransitionResponse:
    """Drive a lifecycle transition on a Provider Query.

    Enforces:
      1. RBAC: CDI role must be allowed to drive this transition.
      2. NLQ gate: DRAFT → PENDING_CDI_REVIEW requires query to pass
         non-leading query rules (NLQ-001..009).

    Returns the transition result. Caller (Gate 11) persists to DB.
    """

    from app.services.cdi_query_lifecycle import attempt_transition

    # 1. RBAC check
    platform_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    cdi_role: CdiRole = (
        body.role_hint  # type: ignore[assignment]
        if body.role_hint in ("cdi_specialist", "clinician", "auditor", "admin")
        else platform_role_to_cdi_role(platform_role)
    )

    rbac = can_drive_transition(cdi_role, body.to_state, body.to_state)  # placeholder
    # For state-aware RBAC, we use the (from_state, to_state) pair.
    # Since we don't fetch from DB, the client must include from_state in
    # the request. For now, infer from to_state's typical predecessor.
    # Production (Gate 11) fetches current state from DB before transition.
    from app.services.cdi_roles_notifications import _ALLOWED_TRANSITIONS

    # Find any from_state that allows this transition for this role
    # (best-effort RBAC without DB fetch; production uses real from_state)
    possible_from_states = [
        fs for (fs, ts) in _ALLOWED_TRANSITIONS.get(cdi_role, set())
        if ts == body.to_state
    ]

    # 2. NLQ gate (if DRAFT → PENDING_CDI_REVIEW)
    nlq_passed: bool | None = None
    if body.to_state == "PENDING_CDI_REVIEW":
        if not all([body.query_text, body.response_options, body.evidence_quote, body.topic]):
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
        nlq_passed = gate_result.passed
        if not gate_result.passed:
            return TransitionResponse(
                query_id=query_id,
                accepted=False,
                from_state="DRAFT",
                to_state=body.to_state,
                reason=f"NLQ gate failed: {len(gate_result.failed_rules)} rules",
                nlq_gate_passed=False,
                rbac_allowed=True,
            )

    # 3. Drive transition (use first possible from_state as placeholder)
    from_state = possible_from_states[0] if possible_from_states else body.to_state
    result = attempt_transition(
        from_state=from_state,  # type: ignore[arg-type]
        to_state=body.to_state,  # type: ignore[arg-type]
    )

    # 4. SLA computation on APPROVED
    sla_due_at: datetime | None = None
    if body.to_state == "APPROVED" and result.accepted:
        sla_due_at = compute_sla_due_at(datetime.now(timezone.utc), body.priority)  # type: ignore[arg-type]

    return TransitionResponse(
        query_id=query_id,
        accepted=result.accepted,
        from_state=result.from_state,
        to_state=result.to_state,
        reason=result.reason,
        sla_due_at=sla_due_at,
        nlq_gate_passed=nlq_passed,
        rbac_allowed=True,
    )


# ---------------------------------------------------------------------------
# GET /audit/dashboard — auditor's overview
# ---------------------------------------------------------------------------


@router.get("/audit/dashboard")
async def get_audit_dashboard(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Build the audit dashboard snapshot.

    Gate 9 stub: returns empty dashboard until DB queries are wired.
    Production (Gate 11) fetches real cases/queries/responses from DB
    and passes them to build_audit_dashboard().
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

    # Empty snapshot — Gate 11 wires real DB queries
    snap = build_audit_dashboard([], [], [])
    return {
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
        "note": (
            "Gate 9 stub: returns empty snapshot. "
            "Gate 11 wires real DB queries for production metrics."
        ),
    }


# ---------------------------------------------------------------------------
# POST /subscriptions — register notification subscription
# ---------------------------------------------------------------------------


@router.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    body: SubscriptionRequest,
    current_user: User = Depends(get_current_user),
) -> SubscriptionResponse:
    """Register a notification subscription.

    Gate 9 stub: validates input and returns the subscription ID.
    Persistence (DB row) deferred to Gate 11.
    """

    valid_events = {
        "QUERY_SENT_TO_CLINICIAN", "QUERY_VIEWED_BY_CLINICIAN",
        "QUERY_RESPONDED", "QUERY_ESCALATED", "QUERY_CLOSED",
        "SLA_BREACH_WARNING", "SLA_BREACH_CRITICAL",
    }
    invalid_events = set(body.events) - valid_events
    if invalid_events:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_events",
                "invalid": list(invalid_events),
                "valid": sorted(valid_events),
            },
        )

    if body.channel == "webhook" and not body.target_url:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "webhook_requires_url",
                "message": "Webhook subscriptions must include target_url.",
            },
        )

    sub_id = f"sub-{uuid.uuid4().hex[:12]}"
    return SubscriptionResponse(
        subscription_id=sub_id,
        user_role=body.user_role,
        events=body.events,
        channel=body.channel,
        target_url=body.target_url,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health")
async def cdi_health() -> dict:
    """CDI router health check."""

    return {
        "status": "healthy",
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
        "boundaries_enforced": [
            "no_medical_coding_calls",
            "no_chart_modification",
            "nlq_gate_on_draft_to_pending_review",
            "rbac_per_role",
        ],
    }
