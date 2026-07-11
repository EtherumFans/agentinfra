"""Usage endpoints with real data from audit logs and transactions.

Phase 5 A3 (2026-07-10): ``/summary`` now aggregates ``run_history.cost_usd``
(legacy column name; the value is CNY per A2 currency unification) so the
page surfaces real LLM cost from agent runs instead of showing ¥0.00 when
no billing-side debit transactions exist. A ``daily_breakdown`` field is
also returned to enable A6's 30-day cost chart on the frontend.
"""
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.run_history import RunHistoryModel
from app.services.token_tracker import global_tracker

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/tokens")
async def get_token_usage():
    """Get real-time LLM token usage since server start."""
    return {"token_usage": global_tracker.snapshot()}


@router.get("/summary")
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary from real audit logs, run_history, and transaction records."""
    since = datetime.now(UTC) - timedelta(days=days)

    result = await db.execute(
        select(func.count(AuditLog.id))
        .where(AuditLog.user_id == user.id)
        .where(AuditLog.created_at >= since)
    )
    total_requests = result.scalar() or 0

    # ── Phase 5 A3: real LLM cost from run_history.cost_usd ────────────────
    # The previous implementation read from Transaction (billing-side debits).
    # Most agent runs don't create debit transactions, so the page showed ¥0.00
    # even when run_history had rows with non-zero cost_usd. Aggregate the
    # actual LLM cost here. (Column name says "usd" for legacy reasons; per
    # Phase 5 A2 the value is CNY. See CLAUDE.md §货币约定.)
    run_cost_result = await db.execute(
        select(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0))
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
    )
    credits_used = round(float(run_cost_result.scalar() or 0.0), 6)

    # Daily breakdown for A6's 30-day bar chart. One row per day with the
    # day's total cost (CNY). Returns as [{"date": "2026-07-01", "cost": 0.0421}, ...].
    daily_result = await db.execute(
        select(
            func.date(RunHistoryModel.created_at).label("day"),
            func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
        )
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
        .group_by(func.date(RunHistoryModel.created_at))
        .order_by(func.date(RunHistoryModel.created_at).asc())
    )
    daily_breakdown = [
        {"date": str(row.day), "cost": round(float(row.cost or 0.0), 6)}
        for row in daily_result
    ]

    # Compute average response time from review processing times
    from app.models.review import CodingReview
    rt_result = await db.execute(
        select(func.avg(CodingReview.processing_time_ms))
        .where(CodingReview.created_at >= since)
    )
    avg_response_time = rt_result.scalar()
    avg_response_time_ms = round(avg_response_time, 0) if avg_response_time else 0

    token_snapshot = global_tracker.snapshot()
    return {
        "total_requests": total_requests,
        "credits_used": credits_used,
        "currency": "CNY",
        "daily_breakdown": daily_breakdown,
        "avg_response_time_ms": avg_response_time_ms,
        "period_days": days,
        "tokens": {
            "prompt": token_snapshot["prompt_tokens"],
            "completion": token_snapshot["completion_tokens"],
            "total": token_snapshot["total_tokens"],
            "llm_calls": token_snapshot["call_count"],
        },
    }


@router.get("/history")
async def get_usage_history(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage history from audit logs"""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )
    logs = result.scalars().all()

    return {
        "history": [
            {
                "date": log.created_at.strftime("%Y-%m-%d %H:%M"),
                "endpoint": log.action,
                "resource_type": log.resource_type,
                "status": log.status,
            }
            for log in logs
        ],
        "total": len(logs),
    }
