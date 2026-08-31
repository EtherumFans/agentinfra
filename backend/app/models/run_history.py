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

    # ── Phase 7 Gate 5 §10.1: partner attribution ───────────────────
    # api_client_id is the OAuthClient.client_id of the partner that
    # initiated the run. NULL for Console JWT users; NON-NULL for
    # partner SDK / embedded widget runs.
    api_client_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True,
    )
    delegated_subject_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True,
    )
    purpose_of_use: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True,
    )
    embedded_app_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    context_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True,
    )

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

    # ── Phase 7 Gate 4 §9.1: run lifecycle status ───────────────────
    # See app.services.run_lifecycle.RunStatus for the enum constants.
    status: Mapped[str] = mapped_column(
        String(48), nullable=False, default="COMPLETED", server_default="COMPLETED",
        index=True,
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancelled_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )

    # ── Phase A1A Gate 2 §2: tenancy classification ──────────────────
    # MODERN | LEGACY_TENANT_KNOWN | LEGACY_TENANT_UNKNOWN | QUARANTINED
    # See alembic 016. NULL on rows written before Gate 2; MODERN on
    # all rows written after (enforced at the service layer).
    #
    # ── Phase A1A Gate 3.1 §3 — extended taxonomy ──
    # Gate 3.1 splits LEGACY_TENANT_KNOWN into:
    #   LEGACY_TENANT_VERIFIED | LEGACY_TENANT_INFERRED | LEGACY_TENANT_AMBIGUOUS
    # so the same column now carries one of seven values. See
    # alembic 017 + app.services.legacy_tenancy_attribution.
    tenancy_classification: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True,
    )

    # ── Phase A1A Gate 3.1 §4 — attribution provenance ──────────────
    # How this row's organization_id was resolved. Nullable because
    # MODERN rows don't need attribution (the write path supplied the
    # org directly). For legacy rows, this is the evidence trail.
    tenancy_attribution_source: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment=(
            "modern_write_path | api_client_binding | session_binding | "
            "context_binding | request_correlation | user_membership_latest "
            "| user_membership_at_time | user_single_membership_history | "
            "security_event | no_user_id_no_candidate | user_id_no_membership"
        ),
    )
    tenancy_attribution_confidence: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        comment="verified | inferred | ambiguous | none",
    )
    tenancy_attribution_migration: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True,
        comment="Which migration last touched this row's attribution (016 or 017).",
    )
    tenancy_attributed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When the attribution was last computed.",
    )
    tenancy_original_org_id: Mapped[Optional[str]] = mapped_column(
        String(12), nullable=True,
        comment="Original organization_id before backfill; NULL means it was always NULL.",
    )
    tenancy_candidate_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="How many candidate orgs were considered; 0 means no candidate, 1 means unambiguous, >1 means ambiguous.",
    )

    # ── Phase A1A Gate 3.3 — trace capture audit ─────────────────────
    # Did this run's trace events actually reach the persistent
    # run_trace_events table?
    #   PERSISTED       — DbRunTraceStore.append succeeded for all events
    #   FAILED          — at least one DB write raised; events may be lost
    #   FALLBACK_MEMORY — store was InMemoryRunTraceStore (dev/test only)
    #   NULL            — row written before Gate 3.3 (backwards compat)
    # When RUNTRACE_FAIL_CLOSED=True, a FAILED run surfaces the error
    # to the caller instead of continuing silently.
    trace_capture_status: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True,
        comment="PERSISTED | FAILED | FALLBACK_MEMORY",
    )
    trace_capture_failure_reason: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Short error string when trace_capture_status=FAILED.",
    )

    # Durable retention tombstone. The trace purge job may remove only an old
    # prefix (or all events) while retaining the RunHistory row. Keeping the
    # purge timestamp/count lets SSE distinguish a random unknown cursor from
    # one that can no longer be resolved after an authorized retention purge.
    trace_events_purged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Most recent authorized run_trace_events retention purge.",
    )
    trace_events_purged_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Cumulative trace event rows removed by retention.",
    )

    # Timestamp for ordering (created_at comes from TimestampMixin)


__all__ = ["RunHistoryModel"]
