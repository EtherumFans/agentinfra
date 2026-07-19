# iCoDer - RunTrace Event Model (Phase 3-D2 Task 1)
"""Persistent RunTrace events.

Phase 3-D1 kept RunTrace in-memory (process-local dict). Phase 3-D2
promotes it to a real DB table so traces survive process restarts,
are visible across workers, and can be org-scoped for audit.

The ``safe_metadata_json`` column is ALREADY display-safe at write
time — ``DbRunTraceStore.append()`` runs a defensive scan (known
secret keys + token-blob heuristic) before insert. If a leak slips
through, the field is blanked + a warning is logged. The contract
is "no raw token / client_secret / Authorization header ever
persists to disk".

Index strategy:
  - ``ix_run_trace_events_run_id`` — point lookup by run_id (the
    primary access pattern for GET /api/runtime/runs/{run_id}/trace)
  - ``ix_run_trace_events_org_created`` — org-scoped audit queries
    (e.g. "show me all traces for org X in the last hour")
  - ``ix_run_trace_events_agent_id`` — per-agent analysis
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RunTraceEventModel(Base, TimestampMixin):
    __tablename__ = "run_trace_events"

    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=True, index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    step: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ts: Mapped[float] = mapped_column(Float, default=0.0)  # epoch seconds
    safe_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Phase A1A Gate 3R.4 — stable event identity ──────────────
    # event_id is a UUID string (canonical identity, stable across
    # process restarts). sequence_number is per-trace_id monotonic
    # ordering. trace_id groups events across multi-trace runs.
    # identity_source records how the identity was assigned so audits
    # can distinguish 3R.4-era events (``"uuid_v4"``) from legacy
    # events (NULL — pre-Migration-020 rows).
    event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sequence_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    identity_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # created_at comes from TimestampMixin; we add a server_default
    # explicitly here so raw SQL inserts (without ORM) still get a value.


__all__ = ["RunTraceEventModel"]
