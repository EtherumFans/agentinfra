# iCoDer A1C.3 — Patient Context API
"""POST/GET/DELETE/extend for /api/v1/patient-context.

Closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT per the A1C.3 HIS/EMR
Integration Contract §2.

Hard rules:
- Cross-tenant access returns 404 (no leak) — A1A Gate 3 tenant_read_policy
- Hard 24h TTL via expires_at — extend cannot exceed total 24h lifetime
- Idempotency-Key dedup — Phase 7 Gate 3 IdempotencyRecord (24h window)
- Audit log emit on create / delete — A1A Gate 3 system_audit allowlist
- Research purpose requires explicit patient-consent (scenario 16)
"""
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.patient_context import PatientContext
from app.schemas.patient_context import (
    PatientContextCreate,
    PatientContextExtend,
    PatientContextResponse,
)
from app.middleware.auth import get_current_user, get_current_organization
from app.middleware.audit import log_action

router = APIRouter(prefix="/api/v1/patient-context", tags=["patient-context (A1C.3)"])

MAX_TTL_SECONDS = 24 * 3600  # PDF §2.3 hard ceiling


@router.post("", response_model=PatientContextResponse, status_code=201)
async def create_patient_context(
    data: PatientContextCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Create a new patient context. 24h TTL enforced."""
    now = datetime.now(timezone.utc)
    # Strip tzinfo for SQLite compatibility (SQLAlchemy DateTime is naive)
    now_naive = now.replace(tzinfo=None)
    expires_naive = now_naive + timedelta(seconds=MAX_TTL_SECONDS)

    ctx = PatientContext(
        organization_id=current_org.id,
        tenant_id=data.tenant_id,
        source_system=data.source_system,
        patient_id=data.patient_id,
        encounter_id=data.encounter_id,
        visit_type=data.visit_type,
        department_id=data.department_id,
        ward_id=data.ward_id,
        clinician_id=data.clinician_id,
        document_ids=data.document_ids,
        purpose_of_use=data.purpose_of_use,
        consent_legal_basis=data.consent_legal_basis,
        trace_id=data.trace_id or f"00-{uuid4().hex}-{uuid4().hex[:16]}-01",
        status="active",
        expires_at=expires_naive,
        created_by=current_user.id,
    )
    db.add(ctx)
    await db.flush()

    await log_action(
        db, current_user.id, current_user.username,
        "patient_context.create",
        "patient_context", ctx.id,
        ip_address=request.client.host if request.client else None,
    )

    await db.refresh(ctx)
    return PatientContextResponse.model_validate(ctx)


@router.get("/{context_id}", response_model=PatientContextResponse)
async def get_patient_context(
    context_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Get a patient context. Cross-tenant returns 404 (no leak)."""
    result = await db.execute(
        select(PatientContext).where(
            PatientContext.id == context_id,
            PatientContext.organization_id == current_org.id,
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise HTTPException(status_code=404, detail={
            "code": "NOT_FOUND", "message": "patient context not found"
        })
    if ctx.status == "deleted":
        raise HTTPException(status_code=410, detail={
            "code": "GONE", "message": "patient context was deleted"
        })
    # Auto-mark expired if past expires_at (lazy TTL)
    if ctx.status == "active" and ctx.expires_at < datetime.utcnow():
        ctx.status = "expired"
        await db.flush()
    return PatientContextResponse.model_validate(ctx)


@router.delete("/{context_id}", status_code=204)
async def delete_patient_context(
    context_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Soft-delete a patient context. Idempotent (DELETE twice → 204)."""
    result = await db.execute(
        select(PatientContext).where(
            PatientContext.id == context_id,
            PatientContext.organization_id == current_org.id,
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        # Cross-tenant or non-existent — both return 404 to avoid leak
        raise HTTPException(status_code=404, detail={
            "code": "NOT_FOUND", "message": "patient context not found"
        })

    if ctx.status != "deleted":
        ctx.status = "deleted"
        await db.flush()
        await log_action(
            db, current_user.id, current_user.username,
            "patient_context.delete",
            "patient_context", ctx.id,
            ip_address=request.client.host if request.client else None,
        )
    return None


@router.post("/{context_id}/extend", response_model=PatientContextResponse)
async def extend_patient_context(
    context_id: str,
    data: PatientContextExtend,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Extend expires_at. Hard cap: total lifetime ≤ 24h from created_at."""
    result = await db.execute(
        select(PatientContext).where(
            PatientContext.id == context_id,
            PatientContext.organization_id == current_org.id,
        )
    )
    ctx = result.scalar_one_or_none()
    if ctx is None:
        raise HTTPException(status_code=404, detail={
            "code": "NOT_FOUND", "message": "patient context not found"
        })
    if ctx.status == "deleted":
        raise HTTPException(status_code=410, detail={
            "code": "GONE", "message": "cannot extend a deleted context"
        })

    new_expires = ctx.expires_at + timedelta(seconds=data.extend_seconds)
    hard_ceiling = ctx.created_at + timedelta(seconds=MAX_TTL_SECONDS)
    if new_expires > hard_ceiling:
        raise HTTPException(status_code=409, detail={
            "code": "STATE_CONFLICT",
            "message": (
                f"extend would exceed 24h hard ceiling "
                f"(created_at={ctx.created_at.isoformat()}, "
                f"requested_expires_at={new_expires.isoformat()}, "
                f"ceiling={hard_ceiling.isoformat()})"
            ),
        })

    ctx.expires_at = new_expires
    if ctx.status == "expired":
        ctx.status = "active"  # extending revives an expired context within 24h window
    await db.flush()
    await log_action(
        db, current_user.id, current_user.username,
        "patient_context.extend",
        "patient_context", ctx.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.refresh(ctx)
    return PatientContextResponse.model_validate(ctx)
