"""Runtime API — human-in-the-loop review + audit chain access.

iCoDer equivalent: "Runtime endpoints for deterministic state management,
human review gates, and compliance audit trail access."
"""
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.runtime import (
    runtime_registry, CaseState, GateOutcome, DUC_ACTIONS
)

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


class HumanReviewRequest(BaseModel):
    case_id: str
    action: str
    rationale: str = ""
    decision: str = "approve"  # approve | reject


@router.get("/status/{case_id}")
async def get_runtime_status(case_id: str, user: User = Depends(get_current_user)):
    """Get the current runtime state for a case."""
    rt = runtime_registry.get(case_id)
    if not rt:
        raise HTTPException(status_code=404, detail="Case not found in runtime")
    return rt.status()


@router.get("/audit/{case_id}")
async def get_audit_trail(
    case_id: str,
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_user),
):
    """Get the audit trail for a case."""
    rt = runtime_registry.get(case_id)
    if not rt:
        raise HTTPException(status_code=404, detail="Case not found in runtime")
    return {"case_id": case_id, "events": rt.audit.get_recent(limit), "total": len(rt.audit)}


@router.post("/review/{case_id}")
async def human_review_decision(
    case_id: str,
    body: HumanReviewRequest,
    user: User = Depends(get_current_user),
):
    """Record a human review decision for a case.

    This is the human-in-the-loop gate. For DUC (Deny-Unless-Confirmed)
    actions, the case cannot proceed until a human confirms via this endpoint.
    """
    rt = runtime_registry.get(case_id)
    if not rt:
        raise HTTPException(status_code=404, detail="Case not found in runtime")

    action = body.action
    if action not in DUC_ACTIONS:
        raise HTTPException(status_code=400, detail=f"'{action}' is not a DUC action")

    if body.decision == "approve":
        rt.human_confirm(action, reviewer=user.full_name or user.username, rationale=body.rationale)
        # Auto-transition to next state if appropriate
        if rt.state == CaseState.REVIEW_REQUIRED and action == "confirm_decision":
            rt.transition(CaseState.DECISION_CONFIRMED, actor=user.full_name or user.username)
        return {"status": "confirmed", "state": rt.state.value}
    else:
        # Reject → keep in REVIEW_REQUIRED
        rt.audit.record("human_rejected",
            actor=user.full_name or user.username,
            payload={"action": action, "rationale": body.rationale}
        )
        return {"status": "rejected", "state": rt.state.value}


@router.get("/duc/actions")
async def list_duc_actions():
    """List all Deny-Unless-Confirmed actions."""
    return {"duc_actions": sorted(DUC_ACTIONS)}


@router.get("/stale")
async def get_stale_cases(
    max_age_hours: float = Query(24.0, ge=1.0),
    user: User = Depends(get_current_user),
):
    """List cases that have been stuck in a state for too long."""
    stale = runtime_registry.stale_cases(max_age_hours)
    return {"stale_cases": stale, "count": len(stale)}


@router.get("/states")
async def list_states():
    """List all case states and their permitted actions."""
    from app.services.runtime import STATE_ACTIONS, STATE_TRANSITIONS
    return {
        "states": [
            {
                "state": s.value,
                "permitted_actions": sorted(STATE_ACTIONS.get(s, set())),
                "allowed_transitions": sorted(t.value for t in STATE_TRANSITIONS.get(s, set())),
            }
            for s in CaseState
        ]
    }


@router.get("/active")
async def get_active_cases(user: User = Depends(get_current_user)):
    """Get all active runtime cases."""
    cases = []
    for case_id, rt in runtime_registry._runtimes.items():
        cases.append({
            "case_id": case_id,
            "state": rt.state.value,
            "duration_s": int(time.time() - rt.state_entered_at),
            "audit_events": len(rt.audit),
        })
    return {"active_cases": cases, "count": len(cases)}


@router.get("/summary/{review_id}")
async def get_review_audit_summary(
    review_id: str,
    current_user=Depends(get_current_user),
):
    """Get live audit summary for a review from in-memory Runtime.

    Aggregates: event counts, guard outcomes, DUC decisions,
    state timeline, warnings. Uses in-memory Runtime if active,
    falls back to DB persistence.
    """
    from sqlalchemy import select as _s
    from app.database import async_session_factory

    # Extract pipeline_id
    pipeline_id = review_id
    for prefix in ("REV-", "INT-", "AR-", "ARS-"):
        if review_id.startswith(prefix):
            pipeline_id = review_id[len(prefix):]
            break

    # Try in-memory Runtime first
    rt = runtime_registry.get(pipeline_id)
    if not rt:
        for rid, r in runtime_registry._runtimes.items():
            if rid == pipeline_id or pipeline_id in rid:
                rt = r
                break

    if rt:
        # Build from in-memory Runtime
        events = rt.audit.get_all()
        event_type_counts = {}
        guard_outcomes = {"ALLOW": 0, "REVIEW": 0, "DENY": 0}
        for e in events:
            et = e.get("event_type", e.get("event_type", "unknown"))
            event_type_counts[et] = event_type_counts.get(et, 0) + 1
            payload = e.get("payload", {})
            outcome = payload.get("outcome", "")
            if outcome in guard_outcomes:
                guard_outcomes[outcome] += 1

        decision_summary = {
            "total_decisions": len(rt._human_confirmations),
            "approved": len(rt._human_confirmations),
            "rejected": 0,
            "actions": sorted(rt._human_confirmations),
        }
        state_timeline = [
            {"from": e.get("payload", {}).get("from", ""),
             "to": e.get("payload", {}).get("to", ""),
             "actor": e.get("actor", ""),
             "timestamp": e.get("timestamp", "")}
            for e in events if e.get("event_type") == "state_transition"
        ]
        warnings = [
            {"type": e.get("event_type"), "actor": e.get("actor", ""),
             "timestamp": e.get("timestamp", "")}
            for e in events
            if e.get("event_type") in ("timeout_escalation", "illegal_transition_attempt", "forced_transition")
        ]
        return {
            "review_id": review_id, "pipeline_id": pipeline_id,
            "source": "memory",
            "session": rt.status(),
            "event_counts": event_type_counts,
            "total_audit_events": len(events),
            "guard_outcomes": guard_outcomes,
            "decision_summary": decision_summary,
            "state_timeline": state_timeline,
            "warnings": warnings,
        }

    # Fallback to DB persistence
    try:
        from app.models.runtime_persistence import (
            RuntimeSession as RTS, RuntimeAuditRecord as RAR,
            RuntimeTransition as RTr, DUCDecision as DUC,
        )
        async with async_session_factory() as db:
            # Find session
            r = await db.execute(_s(RTS).where(
                (RTS.runtime_id == pipeline_id) | (RTS.review_id == review_id)
            ))
            session = r.scalar_one_or_none()

            # Audit records
            r2 = await db.execute(_s(RAR).where(RAR.runtime_id == pipeline_id).order_by(RAR.created_at))
            audit_recs = r2.scalars().all()

            r3 = await db.execute(_s(RTr).where(RTr.runtime_id == pipeline_id).order_by(RTr.created_at))
            transitions = r3.scalars().all()

            r4 = await db.execute(_s(DUC).where(DUC.runtime_id == pipeline_id).order_by(DUC.created_at))
            ducs = r4.scalars().all()

            event_type_counts = {}
            guard_outcomes = {"ALLOW": 0, "REVIEW": 0, "DENY": 0}
            for rec in audit_recs:
                event_type_counts[rec.event_type] = event_type_counts.get(rec.event_type, 0) + 1
                if rec.guard_result and rec.guard_result in guard_outcomes:
                    guard_outcomes[rec.guard_result] += 1
                if rec.post_check_result and rec.post_check_result in guard_outcomes:
                    guard_outcomes[rec.post_check_result] += 1

            decision_summary = {
                "total_decisions": len(ducs),
                "approved": sum(1 for d in ducs if d.decision == "approved"),
                "rejected": sum(1 for d in ducs if d.decision == "rejected"),
                "decisions": [
                    {"action": d.action, "reviewer": d.reviewer,
                     "decision": d.decision, "reason": d.reason,
                     "created_at": d.created_at.isoformat() if d.created_at else None}
                    for d in ducs
                ],
            }
            state_timeline = [
                {"from": t.from_state, "to": t.to_state,
                 "type": t.transition_type, "actor": t.actor, "reason": t.reason,
                 "created_at": t.created_at.isoformat() if t.created_at else None}
                for t in transitions
            ]
            warnings = [
                {"type": rec.event_type, "actor": rec.actor,
                 "state": rec.current_state,
                 "created_at": rec.created_at.isoformat() if rec.created_at else None}
                for rec in audit_recs
                if rec.event_type in ("timeout_escalation", "illegal_transition_attempt", "forced_transition")
            ]
            session_data = {
                "current_state": session.current_state if session else None,
                "execution_path": session.execution_path if session else None,
                "escalated": session.escalated if session else False,
                "failed": session.failed if session else False,
                "archived": session.archived if session else False,
            } if session else None

            return {
                "review_id": review_id, "pipeline_id": pipeline_id,
                "source": "db",
                "session": session_data,
                "event_counts": event_type_counts,
                "total_audit_events": len(audit_recs),
                "total_transitions": len(transitions),
                "guard_outcomes": guard_outcomes,
                "decision_summary": decision_summary,
                "state_timeline": state_timeline,
                "warnings": warnings,
            }
    except Exception as e:
        return {
            "review_id": review_id, "pipeline_id": pipeline_id,
            "source": "none",
            "error": str(e),
            "event_counts": {}, "guard_outcomes": {},
            "decision_summary": {"total_decisions": 0, "approved": 0, "rejected": 0},
            "state_timeline": [], "warnings": [],
        }
