"""Opt-in development preauthorization and idempotent Agent Run settlement.

This is deliberately a local-ledger simulation, not a payment processor.  It
is disabled by default and cannot be enabled outside local/development modes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.audit import log_action
from app.models.billing import Transaction
from app.models.billing_run_settlement import BillingRunSettlement
from app.models.user import User


RESERVED = "RESERVED"
SETTLING = "SETTLING"
SETTLED = "SETTLED"
SETTLEMENT_FAILED = "SETTLEMENT_FAILED"
RELEASED = "RELEASED"
_HELD_STATUSES = (RESERVED, SETTLING, SETTLEMENT_FAILED)


def billing_principal_lock_statement(user_id: str):
    """Return the portable owner-row lock used to serialize ledger writes.

    PostgreSQL emits ``FOR UPDATE`` and keeps the lock until the request-scoped
    transaction commits. SQLite intentionally treats it as a no-op; production
    concurrency still requires PostgreSQL verification.
    """

    return select(User.id).where(User.id == user_id).with_for_update()


async def lock_billing_principal(db: AsyncSession, user_id: str) -> None:
    locked = await db.scalar(billing_principal_lock_statement(user_id))
    if locked is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_BILLING_PRINCIPAL_UNSUPPORTED"},
        )


def run_billing_enabled() -> bool:
    if settings.APP_ENV not in {"local", "development", "dev"}:
        return False
    simulation_enabled = os.environ.get("ICODER_BILLING_SIMULATION", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }
    return simulation_enabled and os.environ.get(
        "ICODER_AGENT_RUN_BILLING_ENFORCED", "false"
    ).strip().lower() in {
        "1", "true", "yes", "on",
    }


def estimate_reserve(input_chars: int) -> float:
    """Return a conservative configuration-backed CNY reservation."""
    try:
        floor = max(float(os.environ.get("ICODER_AGENT_RUN_RESERVE_CNY", "0.05")), 0.0)
    except ValueError:
        floor = 0.05
    try:
        calls = min(
            max(int(os.environ.get("ICODER_AGENT_RUN_MAX_MODEL_CALLS", "5")), 1),
            16,
        )
    except ValueError:
        calls = 5
    # Allow for Pack prompts/tool results in addition to user input.  The
    # configurable floor remains the primary operator safety margin.
    input_tokens_max = (max(int(input_chars), 0) + 8192) * calls
    output_tokens_max = max(int(settings.LLM_MAX_TOKENS), 1) * calls
    derived = (
        input_tokens_max * max(float(settings.LLM_PRICE_INPUT_PER_1M), 0.0)
        + output_tokens_max * max(float(settings.LLM_PRICE_OUTPUT_PER_1M), 0.0)
    ) / 1_000_000
    return round(max(floor, derived), 6)


async def ledger_balance(
    db: AsyncSession, *, organization_id: str, user_id: str,
) -> float:
    value = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            Transaction.organization_id == organization_id,
            Transaction.user_id == user_id,
        )
    )
    return round(float(value or 0.0), 6)


async def held_reservations(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    exclude_run_id: str = "",
) -> float:
    stmt = select(
        func.coalesce(func.sum(BillingRunSettlement.reserved_amount), 0.0)
    ).where(
        BillingRunSettlement.organization_id == organization_id,
        BillingRunSettlement.user_id == user_id,
        BillingRunSettlement.status.in_(_HELD_STATUSES),
    )
    if exclude_run_id:
        stmt = stmt.where(BillingRunSettlement.run_id != exclude_run_id)
    value = await db.scalar(stmt)
    return round(float(value or 0.0), 6)


async def available_balance(
    db: AsyncSession, *, organization_id: str, user_id: str,
) -> tuple[float, float, float]:
    balance = await ledger_balance(
        db, organization_id=organization_id, user_id=user_id,
    )
    held = await held_reservations(
        db, organization_id=organization_id, user_id=user_id,
    )
    return balance, held, round(balance - held, 6)


async def preauthorize_run(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    username: str | None,
    run_id: str,
    input_chars: int,
) -> BillingRunSettlement | None:
    if not run_billing_enabled():
        return None
    if not organization_id or not user_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "RUN_BILLING_PRINCIPAL_UNSUPPORTED"},
        )

    await lock_billing_principal(db, user_id)

    existing = await db.scalar(
        select(BillingRunSettlement).where(
            BillingRunSettlement.organization_id == organization_id,
            BillingRunSettlement.run_id == run_id,
        )
    )
    if existing is not None:
        return existing

    reserve = estimate_reserve(input_chars)
    balance, held, available = await available_balance(
        db, organization_id=organization_id, user_id=user_id,
    )
    if available < reserve:
        await log_action(
            db,
            user_id,
            username,
            "billing.run.preauthorization_denied",
            "billing_run_settlement",
            run_id,
            details={
                "run_id": run_id,
                "reserved_amount": reserve,
                "balance": balance,
                "held_amount": held,
                "available_balance": available,
                "currency": "CNY",
                "simulation": True,
                "error_code": "INSUFFICIENT_CREDITS",
            },
            organization_id=organization_id,
            status="failure",
        )
        raise HTTPException(
            status_code=402,
            detail={
                "code": "INSUFFICIENT_CREDITS",
                "run_id": run_id,
                "balance": balance,
                "reserved": held,
                "available": available,
                "required": reserve,
                "currency": "CNY",
                "simulation": True,
            },
        )

    settlement = BillingRunSettlement(
        organization_id=organization_id,
        user_id=user_id,
        run_id=run_id,
        status=RESERVED,
        reserved_amount=reserve,
        settled_amount=0.0,
        currency="CNY",
    )
    db.add(settlement)
    await db.flush()
    await log_action(
        db,
        user_id,
        username,
        "billing.run.preauthorized",
        "billing_run_settlement",
        settlement.id,
        details={
            "run_id": run_id,
            "reserved_amount": reserve,
            "available_balance": round(available - reserve, 6),
            "currency": "CNY",
            "simulation": True,
        },
        organization_id=organization_id,
    )
    return settlement


@dataclass(frozen=True)
class SettlementOutcome:
    success: bool
    status: str
    reserved_amount: float
    settled_amount: float
    balance_after: float
    error_code: str = ""

    def to_dict(self) -> dict:
        return {
            "simulation": True,
            "status": self.status,
            "reserved_amount": round(self.reserved_amount, 6),
            "settled_amount": round(self.settled_amount, 6),
            "balance_after": round(self.balance_after, 6),
            "currency": "CNY",
            "error_code": self.error_code or None,
        }


@dataclass(frozen=True)
class ReconciliationOutcome:
    released: int
    marked_retryable: int
    skipped_active: int
    inspected: int
    older_than_seconds: int

    def to_dict(self) -> dict:
        return {
            "simulation": True,
            "released": self.released,
            "marked_retryable": self.marked_retryable,
            "skipped_active": self.skipped_active,
            "inspected": self.inspected,
            "older_than_seconds": self.older_than_seconds,
        }


async def reconcile_stale_reservations(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    username: str | None,
    older_than_seconds: int = 3600,
) -> ReconciliationOutcome | None:
    """Release crash-orphaned reservations without touching active Runs.

    This is an explicit development operator action. Rows younger than the
    threshold and rows whose RunHistory remains non-terminal are untouched.
    Orphaned RESERVED rows are released; orphaned SETTLING rows keep their
    hold and become retryable SETTLEMENT_FAILED rows so recorded Provider cost
    is never waived. Existing settlement failures awaiting top-up are excluded.
    """

    if not run_billing_enabled():
        return None
    await lock_billing_principal(db, user_id)
    threshold = min(max(int(older_than_seconds), 300), 604800)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=threshold)
    ).replace(tzinfo=None)
    rows = (
        await db.execute(
            select(BillingRunSettlement).where(
                BillingRunSettlement.organization_id == organization_id,
                BillingRunSettlement.user_id == user_id,
                BillingRunSettlement.status.in_((RESERVED, SETTLING)),
                BillingRunSettlement.updated_at < cutoff,
            )
        )
    ).scalars().all()

    from app.models.run_history import RunHistoryModel
    from app.services.run_lifecycle import RunStatus

    released = 0
    marked_retryable = 0
    skipped_active = 0
    for row in rows:
        run_status = await db.scalar(
            select(RunHistoryModel.status).where(
                RunHistoryModel.organization_id == organization_id,
                RunHistoryModel.run_id == row.run_id,
            )
        )
        if run_status and not RunStatus.is_terminal(run_status):
            skipped_active += 1
            continue
        if row.status == SETTLING:
            row.status = SETTLEMENT_FAILED
            row.error_code = "STALE_SETTLING_REQUIRES_RETRY"
            action = "billing.run.stale_settlement_marked_retryable"
            marked_retryable += 1
        else:
            row.status = RELEASED
            row.error_code = "STALE_RESERVATION_RELEASED"
            action = "billing.run.stale_reservation_released"
            released += 1
        await log_action(
            db,
            user_id,
            username,
            action,
            "billing_run_settlement",
            row.id,
            details={
                "run_id": row.run_id,
                "status": row.status,
                "reserved_amount": round(float(row.reserved_amount), 6),
                "currency": row.currency,
                "simulation": True,
                "error_code": row.error_code,
            },
            organization_id=organization_id,
        )
    await db.flush()
    return ReconciliationOutcome(
        released=released,
        marked_retryable=marked_retryable,
        skipped_active=skipped_active,
        inspected=len(rows),
        older_than_seconds=threshold,
    )


async def settle_run(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    username: str | None,
    run_id: str,
    actual_cost: float,
) -> SettlementOutcome | None:
    if not run_billing_enabled():
        return None
    await lock_billing_principal(db, user_id)
    settlement = await db.scalar(
        select(BillingRunSettlement).where(
            BillingRunSettlement.organization_id == organization_id,
            BillingRunSettlement.user_id == user_id,
            BillingRunSettlement.run_id == run_id,
        )
    )
    if settlement is None:
        raise RuntimeError("billing reservation missing for Agent Run")
    balance = await ledger_balance(
        db, organization_id=organization_id, user_id=user_id,
    )
    if settlement.status == SETTLED:
        return SettlementOutcome(
            True, SETTLED, settlement.reserved_amount,
            settlement.settled_amount, balance,
        )

    cost = round(max(float(actual_cost or 0.0), 0.0), 6)
    claim = await db.execute(
        update(BillingRunSettlement)
        .where(
            BillingRunSettlement.id == settlement.id,
            BillingRunSettlement.status.in_((RESERVED, SETTLEMENT_FAILED)),
        )
        .values(status=SETTLING, settled_amount=cost, error_code=None)
    )
    if claim.rowcount != 1:
        await db.refresh(settlement)
        return SettlementOutcome(
            settlement.status == SETTLED,
            settlement.status,
            settlement.reserved_amount,
            settlement.settled_amount,
            balance,
            settlement.error_code or "SETTLEMENT_IN_PROGRESS",
        )

    other_held = await held_reservations(
        db,
        organization_id=organization_id,
        user_id=user_id,
        exclude_run_id=run_id,
    )
    available_for_run = round(balance - other_held, 6)
    if available_for_run < cost:
        await db.execute(
            update(BillingRunSettlement)
            .where(BillingRunSettlement.id == settlement.id)
            .values(
                status=SETTLEMENT_FAILED,
                settled_amount=cost,
                error_code="INSUFFICIENT_CREDITS_AT_SETTLEMENT",
            )
        )
        await log_action(
            db,
            user_id,
            username,
            "billing.run.settlement_failed",
            "billing_run_settlement",
            settlement.id,
            details={
                "run_id": run_id,
                "reserved_amount": settlement.reserved_amount,
                "settled_amount": cost,
                "balance": balance,
                "held_amount": other_held,
                "available_balance": available_for_run,
                "currency": "CNY",
                "simulation": True,
                "error_code": "INSUFFICIENT_CREDITS_AT_SETTLEMENT",
            },
            organization_id=organization_id,
            status="failure",
        )
        return SettlementOutcome(
            False, SETTLEMENT_FAILED, settlement.reserved_amount, cost,
            balance, "INSUFFICIENT_CREDITS_AT_SETTLEMENT",
        )

    balance_after = round(balance - cost, 6)
    if cost > 0:
        db.add(Transaction(
            organization_id=organization_id,
            user_id=user_id,
            type="debit",
            amount=-cost,
            balance_after=balance_after,
            description="Agent Run settlement",
            source="api_usage",
        ))
    await db.execute(
        update(BillingRunSettlement)
        .where(BillingRunSettlement.id == settlement.id)
        .values(status=SETTLED, settled_amount=cost, error_code=None)
    )
    await log_action(
        db,
        user_id,
        username,
        "billing.run.settled",
        "billing_run_settlement",
        settlement.id,
        details={
            "run_id": run_id,
            "reserved_amount": settlement.reserved_amount,
            "settled_amount": cost,
            "new_balance": balance_after,
            "currency": "CNY",
            "simulation": True,
            "source": "api_usage",
        },
        organization_id=organization_id,
    )
    return SettlementOutcome(
        True, SETTLED, settlement.reserved_amount, cost, balance_after,
    )


__all__ = [
    "BillingRunSettlement", "ReconciliationOutcome", "SettlementOutcome",
    "available_balance",
    "billing_principal_lock_statement", "estimate_reserve", "held_reservations",
    "ledger_balance", "lock_billing_principal",
    "preauthorize_run", "reconcile_stale_reservations",
    "run_billing_enabled", "settle_run",
]
