"""Billing endpoints with real database persistence.

The local development ledger is deliberately explicit: it can simulate
credits/debits for quota and UI tests, but cloud mode rejects those mutation
endpoints until a real payment/settlement provider is integrated.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.config import settings
from app.middleware.audit import log_action
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.models.billing import Transaction
from app.models.billing_run_settlement import BillingRunSettlement

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _simulation_enabled() -> bool:
    """Return whether local ledger simulation is explicitly available."""

    if settings.APP_ENV not in {"local", "development", "dev"}:
        return False
    return os.environ.get("ICODER_BILLING_SIMULATION", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _low_balance_threshold() -> float:
    raw = os.environ.get("ICODER_BILLING_LOW_BALANCE_THRESHOLD", "5")
    try:
        return max(0.0, round(float(raw), 6))
    except ValueError:
        return 5.0


def _balance_payload(balance: float, reserved: float = 0.0) -> dict:
    threshold = _low_balance_threshold()
    available = round(balance - reserved, 6)
    return {
        "balance": round(balance, 6),
        "reserved": round(reserved, 6),
        "available": available,
        "currency": "CNY",
        "simulation": _simulation_enabled(),
        "ledger_authoritative": not _simulation_enabled(),
        "quota": {
            "kind": "credits",
            "limit": None,
            "remaining": available,
            "enforced": True,
        },
        "alerts": {
            "low_balance": available <= threshold,
            "threshold": threshold,
        },
    }


async def _get_balance(
    user_id: str,
    db: AsyncSession,
    organization_id: str | None = None,
) -> float:
    """Get current balance as the ledger sum, or real zero if none.

    Summing signed transaction amounts is deterministic even when SQLite
    timestamps have coarse precision and multiple entries share a timestamp;
    it also makes the overdraft check independent of display ordering.
    """
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
        Transaction.user_id == user_id,
    )
    if organization_id:
        stmt = stmt.where(Transaction.organization_id == organization_id)
    result = await db.execute(stmt)
    return float(result.scalar() or 0.0)


@router.get("/balance")
async def get_balance(
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get current credit balance"""
    balance = await _get_balance(user.id, db, current_org.id)
    from app.services.run_billing_settlement import held_reservations

    reserved = await held_reservations(
        db, organization_id=current_org.id, user_id=user.id,
    )
    return _balance_payload(balance, reserved)


@router.get("/transactions")
async def get_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get transaction history with real page-number pagination.

    ``limit`` is retained for the existing frontend and means the first page.
    New consumers should use ``page`` and ``page_size``.
    """
    effective_page = 1 if limit is not None else page
    effective_page_size = limit if limit is not None else page_size
    scope = (
        Transaction.user_id == user.id,
        Transaction.organization_id == current_org.id,
    )
    total = int(
        (
            await db.execute(
                select(func.count(Transaction.id)).where(*scope)
            )
        ).scalar_one()
    )
    result = await db.execute(
        select(Transaction)
        .where(*scope)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset((effective_page - 1) * effective_page_size)
        .limit(effective_page_size)
    )
    transactions = result.scalars().all()
    return {
        "transactions": [
            {
                "id": t.id,
                "date": t.created_at.strftime("%Y-%m-%d"),
                "description": t.description,
                "amount": f"¥{t.amount:+.2f}",
                "type": t.type,
                "source": t.source,
                "balance_after": t.balance_after,
            }
            for t in transactions
        ],
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
    }


@router.post("/credits")
async def add_credits(
    amount: float = Query(50.0, gt=0),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Add development credits; real payment integration is not present."""
    if not _simulation_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "BILLING_SIMULATION_DISABLED"},
        )
    from app.services.run_billing_settlement import lock_billing_principal

    await lock_billing_principal(db, user.id)
    current = await _get_balance(user.id, db, current_org.id)
    new_balance = current + amount
    txn = Transaction(
        organization_id=current_org.id,
        user_id=user.id,
        type="credit",
        amount=amount,
        balance_after=new_balance,
        description=f"Credit purchase",
        source="purchase",
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    await log_action(
        db,
        user.id,
        user.username,
        "billing.credit.simulation",
        "billing_ledger",
        txn.id,
        details={
            "amount": round(amount, 6),
            "balance_before": round(current, 6),
            "new_balance": round(new_balance, 6),
            "simulation": True,
            "source": "purchase",
        },
        organization_id=current_org.id,
    )
    await db.commit()
    return {
        "status": "success",
        "added": round(amount, 6),
        "new_balance": round(new_balance, 6),
        "simulation": True,
    }


class SimulationDebitRequest(BaseModel):
    amount: float = Field(gt=0, le=10000)
    reference: str = Field(min_length=1, max_length=128)


@router.post("/simulation/debit")
async def simulate_debit(
    body: SimulationDebitRequest,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Debit the local ledger for quota/alert tests, failing closed on overdraft."""
    if not _simulation_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "BILLING_SIMULATION_DISABLED"},
        )
    amount = round(float(body.amount), 6)
    from app.services.run_billing_settlement import (
        held_reservations,
        lock_billing_principal,
    )

    await lock_billing_principal(db, user.id)
    current = await _get_balance(user.id, db, current_org.id)
    reserved = await held_reservations(
        db, organization_id=current_org.id, user_id=user.id,
    )
    available = round(current - reserved, 6)
    if available < amount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INSUFFICIENT_CREDITS",
                "balance": round(current, 6),
                "reserved": reserved,
                "available": available,
                "required": amount,
            },
        )
    new_balance = round(current - amount, 6)
    txn = Transaction(
        organization_id=current_org.id,
        user_id=user.id,
        type="debit",
        amount=-amount,
        balance_after=new_balance,
        description=f"Development simulation: {body.reference}",
        source="simulation",
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    await log_action(
        db,
        user.id,
        user.username,
        "billing.debit.simulation",
        "billing_ledger",
        txn.id,
        details={
            "amount": amount,
            "balance_before": round(current, 6),
            "new_balance": new_balance,
            "reference": body.reference,
            "simulation": True,
            "source": "simulation",
        },
        organization_id=current_org.id,
    )
    await db.commit()
    return {
        "status": "success",
        "debited": amount,
        "new_balance": new_balance,
        "simulation": True,
        "quota": _balance_payload(new_balance, reserved)["quota"],
        "alerts": _balance_payload(new_balance, reserved)["alerts"],
    }


@router.get("/run-settlements")
async def get_run_settlements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Return PHI-free development settlement state for the current user."""
    effective_page = 1 if limit is not None else page
    effective_page_size = limit if limit is not None else page_size
    scope = (
        BillingRunSettlement.organization_id == current_org.id,
        BillingRunSettlement.user_id == user.id,
    )
    total = int(
        (
            await db.execute(
                select(func.count(BillingRunSettlement.id)).where(*scope)
            )
        ).scalar_one()
    )
    rows = (
        await db.execute(
            select(BillingRunSettlement)
            .where(*scope)
            .order_by(
                BillingRunSettlement.created_at.desc(),
                BillingRunSettlement.id.desc(),
            )
            .offset((effective_page - 1) * effective_page_size)
            .limit(effective_page_size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "run_id": row.run_id,
                "status": row.status,
                "reserved_amount": round(float(row.reserved_amount), 6),
                "settled_amount": round(float(row.settled_amount), 6),
                "currency": row.currency,
                "error_code": row.error_code,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total": total,
        "page": effective_page,
        "page_size": effective_page_size,
        "simulation": _simulation_enabled(),
    }


@router.post("/run-settlements/{run_id}/retry")
async def retry_run_settlement(
    run_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Retry an idempotent failed development settlement after top-up."""
    from app.services.run_billing_settlement import run_billing_enabled, settle_run

    if not run_billing_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RUN_BILLING_SIMULATION_DISABLED"},
        )
    row = await db.scalar(
        select(BillingRunSettlement).where(
            BillingRunSettlement.organization_id == current_org.id,
            BillingRunSettlement.user_id == user.id,
            BillingRunSettlement.run_id == run_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "SETTLEMENT_NOT_FOUND"})
    outcome = await settle_run(
        db,
        organization_id=current_org.id,
        user_id=user.id,
        username=user.username,
        run_id=run_id,
        actual_cost=float(row.settled_amount or 0.0),
    )
    await db.commit()
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RUN_BILLING_SIMULATION_DISABLED"},
        )
    if not outcome.success:
        raise HTTPException(status_code=409, detail=outcome.to_dict())
    return outcome.to_dict()


@router.post("/run-settlements/reconcile-stale")
async def reconcile_stale_run_settlements(
    older_than_seconds: int = Query(3600, ge=300, le=604800),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Reconcile old crash-orphaned local reservations.

    Active RunHistory states and settlement failures awaiting top-up are
    never released; stale in-flight settlements become retryable.
    """

    from app.services.run_billing_settlement import (
        reconcile_stale_reservations,
        run_billing_enabled,
    )

    if not run_billing_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RUN_BILLING_SIMULATION_DISABLED"},
        )
    outcome = await reconcile_stale_reservations(
        db,
        organization_id=current_org.id,
        user_id=user.id,
        username=user.username,
        older_than_seconds=older_than_seconds,
    )
    await db.commit()
    if outcome is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "RUN_BILLING_SIMULATION_DISABLED"},
        )
    return outcome.to_dict()
