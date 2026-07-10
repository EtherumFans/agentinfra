# iCoDer - RunHistory Model (Phase 4-G #3)
"""Persistent per-run summary records.

Phase 4-G #3 (2026-07-10): the unified Agent Run endpoint (POST /api/v1/agents/{id}/run)
writes one row per run so AgentChatPage can hydrate a history dropdown on
page load. Columns mirror AgentRunResponse's most useful summary fields:

  - run_id (foreign-keyed to run_trace_events.run_id for trace hydration)
  - agent_id, runtime_mode, latency_ms, cost_usd (run envelope)
  - input_text (truncated to 4KB to bound row size), output_summary
  - error flag + error_reason for surfacing failed runs in the history list

Indexes:
  - ``ix_run_history_agent_created`` — per-agent recent-runs query (the
    primary access pattern: GET /api/runtime/runs/history?agent_id=X&limit=50)
  - ``ix_run_history_user_created`` — per-user history (current user's
    dropdown across all agents)
  - ``ix_run_history_org_created`` — org-scoped audit
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class RunHistoryModel(Base, TimestampMixin):
    """One row per agent run. Hydrates AgentChatPage's history dropdown."""

    __tablename__ = "run_history"

    # Stable identifiers (indexed for the 3 primary access patterns)
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=True, index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Run envelope fields (from AgentRunResponse)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    runtime_mode: Mapped[str] = mapped_column(String(48), default="", server_default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0.0")

    # Input/output (input_text truncated to bound row size)
    input_text: Mapped[str] = mapped_column(Text, default="")
    output_summary: Mapped[str] = mapped_column(Text, default="")

    # Error tracking (so failed runs can surface in history list)
    error: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    error_reason: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Timestamp for ordering (created_at comes from TimestampMixin)


__all__ = ["RunHistoryModel"]
