"""Usage endpoints with real data from audit logs and transactions.

Phase 5 A3 (2026-07-10): ``/summary`` now aggregates ``run_history.cost_usd``
(legacy column name; the value is CNY per A2 currency unification) so the
page surfaces real LLM cost from agent runs instead of showing ¥0.00 when
no billing-side debit transactions exist. A ``daily_breakdown`` field is
also returned to enable A6's 30-day cost chart on the frontend.

Phase 6 Gate 8 (2026-07-13): multi-dim filters added. ``/summary`` now
accepts optional ``agent_id`` and ``runtime_mode`` query params so the
Usage page can drill into per-agent / per-mode cost. New endpoint
``/by-agent`` returns a per-agent cost breakdown for the requested window.

Phase 7 Gate 8 (2026-07-14): API Client attribution closed loop. With
Gate 5's ``run_history.api_client_id`` column populated, ``/summary`` and
``/by-agent`` now accept an ``api_client_id`` filter, and a new
``/by-client`` endpoint returns per-API-client cost for the "which
partner is spending what?" chart. Filters compose — combine
``api_client_id`` + ``agent_id`` to see "partner X's spend on agent Y".
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
    agent_id: str | None = Query(
        None,
        description=(
            "Phase 6 Gate 8: filter by agent_id (e.g. 'medical-coding-agent'). "
            "If omitted, aggregates across all agents."
        ),
    ),
    runtime_mode: str | None = Query(
        None,
        description=(
            "Phase 6 Gate 8: filter by runtime_mode ('corti_like_fast' / "
            "'medcoder_deep'). If omitted, aggregates across all modes."
        ),
    ),
    api_client_id: str | None = Query(
        None,
        description=(
            "Phase 7 Gate 8: filter by api_client_id (the OAuth client_id "
            "of the partner that initiated the run). Use 'console' (case-"
            "insensitive sentinel) to filter to Console-only runs (api_client_id "
            "IS NULL). If omitted, aggregates across all clients."
        ),
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage summary from real audit logs, run_history, and transaction records.

    Phase 6 Gate 8: ``agent_id`` and ``runtime_mode`` filters apply to the
    run_history aggregation only (audit_log.total_requests is unfiltered
    because audit events don't carry runtime_mode).

    Phase 7 Gate 8: ``api_client_id`` filter applies to run_history only.
    The sentinel value ``"console"`` filters to api_client_id IS NULL
    (runs initiated via Console JWT, not by a partner SDK).
    """
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
    # Phase A1A Gate 3.2 §1 — exclude non-tenant-visible rows from every
    # aggregate. Without this filter, costs from QUARANTINED / UNKNOWN
    # rows would leak into the tenant's usage summary.
    from app.services.tenant_read_policy import apply_tenant_visibility_filter

    cost_query = (
        select(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0))
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
    )
    cost_query = apply_tenant_visibility_filter(
        cost_query, RunHistoryModel.tenancy_classification,
    )
    if agent_id:
        cost_query = cost_query.where(RunHistoryModel.agent_id == agent_id)
    if runtime_mode:
        cost_query = cost_query.where(RunHistoryModel.runtime_mode == runtime_mode)
    if api_client_id:
        if api_client_id.lower() == "console":
            cost_query = cost_query.where(RunHistoryModel.api_client_id.is_(None))
        else:
            cost_query = cost_query.where(
                RunHistoryModel.api_client_id == api_client_id
            )
    run_cost_result = await db.execute(cost_query)
    credits_used = round(float(run_cost_result.scalar() or 0.0), 6)

    # Daily breakdown for A6's 30-day bar chart. One row per day with the
    # day's total cost (CNY). Returns as [{"date": "2026-07-01", "cost": 0.0421}, ...].
    daily_query = (
        select(
            func.date(RunHistoryModel.created_at).label("day"),
            func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
        )
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
        .group_by(func.date(RunHistoryModel.created_at))
        .order_by(func.date(RunHistoryModel.created_at).asc())
    )
    daily_query = apply_tenant_visibility_filter(
        daily_query, RunHistoryModel.tenancy_classification,
    )
    if agent_id:
        daily_query = daily_query.where(RunHistoryModel.agent_id == agent_id)
    if runtime_mode:
        daily_query = daily_query.where(RunHistoryModel.runtime_mode == runtime_mode)
    if api_client_id:
        if api_client_id.lower() == "console":
            daily_query = daily_query.where(RunHistoryModel.api_client_id.is_(None))
        else:
            daily_query = daily_query.where(
                RunHistoryModel.api_client_id == api_client_id
            )
    daily_result = await db.execute(daily_query)
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
        # Phase 6/7 Gate 8: echo back the applied filters so the frontend can
        # display "filtered by agent_id=X / runtime_mode=Y / api_client_id=Z"
        # in the UI.
        "filters": {
            "agent_id": agent_id,
            "runtime_mode": runtime_mode,
            "api_client_id": api_client_id,
        },
        "tokens": {
            "prompt": token_snapshot["prompt_tokens"],
            "completion": token_snapshot["completion_tokens"],
            "total": token_snapshot["total_tokens"],
            "llm_calls": token_snapshot["call_count"],
        },
    }


@router.get("/by-agent")
async def get_usage_by_agent(
    days: int = Query(30, ge=1, le=365),
    api_client_id: str | None = Query(
        None,
        description=(
            "Phase 7 Gate 8: filter by api_client_id. Sentinel 'console' "
            "filters to api_client_id IS NULL."
        ),
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase 6 Gate 8 — per-agent cost breakdown.

    Returns one row per agent_id with cost, run_count, avg_latency_ms.
    Useful for a "which agent is most expensive?" chart on the Usage page.

    Phase 7 Gate 8: optional ``api_client_id`` filter to scope to a single
    partner (or to Console-only runs via the ``"console"`` sentinel).
    """
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            RunHistoryModel.agent_id.label("agent_id"),
            func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
            func.count(RunHistoryModel.run_id).label("run_count"),
            func.coalesce(func.avg(RunHistoryModel.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
        .group_by(RunHistoryModel.agent_id)
        .order_by(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).desc())
    )
    # Phase A1A Gate 3.2 §1 — exclude non-tenant-visible rows.
    from app.services.tenant_read_policy import apply_tenant_visibility_filter
    stmt = apply_tenant_visibility_filter(
        stmt, RunHistoryModel.tenancy_classification,
    )
    if api_client_id:
        if api_client_id.lower() == "console":
            stmt = stmt.where(RunHistoryModel.api_client_id.is_(None))
        else:
            stmt = stmt.where(RunHistoryModel.api_client_id == api_client_id)
    result = await db.execute(stmt)
    rows = result.all()
    return {
        "items": [
            {
                "agent_id": row.agent_id,
                "cost": round(float(row.cost or 0.0), 6),
                "run_count": int(row.run_count or 0),
                "avg_latency_ms": round(float(row.avg_latency_ms or 0), 0),
            }
            for row in rows
        ],
        "total_cost": round(sum(float(r.cost or 0.0) for r in rows), 6),
        "currency": "CNY",
        "period_days": days,
        "filters": {
            "api_client_id": api_client_id,
        },
    }


@router.get("/by-client")
async def get_usage_by_client(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase 7 Gate 8 — per-API-client cost breakdown.

    Returns one row per ``api_client_id`` with cost, run_count, avg_latency_ms.
    The synthetic row ``"console"`` (api_client_id IS NULL) represents runs
    initiated via the Console SPA (JWT auth, no partner attribution).

    Useful for a "which partner is spending what?" chart on the Usage page.
    The chart helps admins decide pricing tiers, spot anomalous spend, and
    reconcile partner invoices against actual consumption.

    Response shape::

        {
          "items": [
            {"api_client_id": "partner-a", "cost": 1.23, "run_count": 45, "avg_latency_ms": 3200},
            {"api_client_id": "console",   "cost": 0.42, "run_count": 18, "avg_latency_ms": 2100},
            ...
          ],
          "total_cost": 1.65,
          "currency": "CNY",
          "period_days": 30
        }
    """
    since = datetime.now(UTC) - timedelta(days=days)
    # We compute two GROUP BY queries: one for partner-attributed runs and
    # one for Console-only (api_client_id IS NULL). The Console bucket is
    # labeled "console" in the response so the UI can render it consistently.
    # Phase A1A Gate 3.2 §1 — exclude non-tenant-visible rows from both.
    from app.services.tenant_read_policy import apply_tenant_visibility_filter
    partner_stmt = (
        select(
            RunHistoryModel.api_client_id.label("api_client_id"),
            func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
            func.count(RunHistoryModel.run_id).label("run_count"),
            func.coalesce(func.avg(RunHistoryModel.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
        .where(RunHistoryModel.api_client_id.is_not(None))
        .group_by(RunHistoryModel.api_client_id)
        .order_by(func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).desc())
    )
    partner_stmt = apply_tenant_visibility_filter(
        partner_stmt, RunHistoryModel.tenancy_classification,
    )
    partner_rows = (await db.execute(partner_stmt)).all()

    console_stmt = (
        select(
            func.coalesce(func.sum(RunHistoryModel.cost_usd), 0.0).label("cost"),
            func.count(RunHistoryModel.run_id).label("run_count"),
            func.coalesce(func.avg(RunHistoryModel.latency_ms), 0).label("avg_latency_ms"),
        )
        .where(RunHistoryModel.user_id == str(user.id))
        .where(RunHistoryModel.created_at >= since)
        .where(RunHistoryModel.api_client_id.is_(None))
    )
    console_stmt = apply_tenant_visibility_filter(
        console_stmt, RunHistoryModel.tenancy_classification,
    )
    console_row = (await db.execute(console_stmt)).one_or_none()

    items = [
        {
            "api_client_id": row.api_client_id,
            "cost": round(float(row.cost or 0.0), 6),
            "run_count": int(row.run_count or 0),
            "avg_latency_ms": round(float(row.avg_latency_ms or 0), 0),
        }
        for row in partner_rows
    ]
    if console_row and int(console_row.run_count or 0) > 0:
        items.append({
            "api_client_id": "console",
            "cost": round(float(console_row.cost or 0.0), 6),
            "run_count": int(console_row.run_count or 0),
            "avg_latency_ms": round(float(console_row.avg_latency_ms or 0), 0),
        })

    return {
        "items": items,
        "total_cost": round(sum(it["cost"] for it in items), 6),
        "currency": "CNY",
        "period_days": days,
    }


@router.get("/history")
async def get_usage_history(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get usage history from audit logs"""
    # Phase A1A Gate 3.2 §1 — exclude non-tenant-visible rows.
    from app.services.tenant_read_policy import apply_tenant_visibility_filter
    stmt = (
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    )
    stmt = apply_tenant_visibility_filter(
        stmt, AuditLog.tenancy_classification, also_exclude_null=True,
    )
    result = await db.execute(stmt)
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
