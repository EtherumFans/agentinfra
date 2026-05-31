"""Usage endpoints with real data from audit logs and transactions."""
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.billing import Transaction
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
    """Get usage summary from real audit logs and transaction records."""
    since = datetime.now(UTC) - timedelta(days=days)

    result = await db.execute(
        select(func.count(AuditLog.id))
        .where(AuditLog.user_id == user.id)
        .where(AuditLog.created_at >= since)
    )
    total_requests = result.scalar() or 0

    # Compute credits used from real debit transactions
    tx_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.user_id == user.id)
        .where(Transaction.type == "debit")
        .where(Transaction.created_at >= since)
    )
    credits_used = round(tx_result.scalar() or 0, 2)

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
