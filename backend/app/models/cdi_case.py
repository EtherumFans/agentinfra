# iCoDer - CDI Case Models (Phase 5 Track D Gate 4)
"""Persistent CDI case + gap + query + response models.

PDF §6 Gate 4 specifies the China CDI capability model:
    CDICase         — top-level per-encounter CDI run
    DocumentationGap  — one gap identified in a case
    ProviderQuery   — one Non-leading query generated for a gap
    ClinicianResponse — clinician's response to a query
    DocumentVersion — snapshot of chart document before/after clarification

Each model is a SQLAlchemy ORM row. Domain dataclasses
(``app.icoder.agent_runtime.cdi.domain``) are the runtime representation;
these models are the persistence representation. Conversion functions
live in ``app.services.cdi_persistence`` (Gate 5).

Indexes (per primary access pattern):
    - per-org recent cases (org + created_at)
    - per-case gap lookup (case_id)
    - per-gap query lookup (gap_id)
    - per-query lifecycle state (lifecycle_state)
    - per-clinician pending queries (clinician_user_id + lifecycle_state)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


# ---------------------------------------------------------------------------
# CDI Case (top-level)
# ---------------------------------------------------------------------------


class CDICaseModel(Base, TimestampMixin):
    """One row per CDI run. Top-level case.

    A case is created when CDI agent runs against a chart. It contains
    0..N gaps; each gap contains 0..1 queries; each query contains 0..1
    clinician responses.
    """

    __tablename__ = "cdi_cases"

    # Identifiers
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    patient_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    encounter_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Chart context (snapshot at time of CDI run)
    chart_excerpt_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    chart_excerpt_length: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    encounter_metadata: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    draft_codes: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")

    # Run linkage
    run_id: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    trace_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    agent_ref: Mapped[str] = mapped_column(
        String(128),
        default="icoder/clinical-documentation-improvement-agent@1.0.0",
        server_default="icoder/clinical-documentation-improvement-agent@1.0.0",
    )

    # Output (6 sections)
    encounter_summary: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    coding_specificity_checklist: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    risk_flags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    specialist_trace: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    query_rewrite_queue: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]",
    )

    # Completion
    completion_state: Mapped[str] = mapped_column(
        String(32), default="REVIEW_REQUIRED", server_default="REVIEW_REQUIRED", index=True,
    )

    # Audit
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Documentation Gap (Section 2)
# ---------------------------------------------------------------------------


class DocumentationGapModel(Base, TimestampMixin):
    """One row per gap identified in a CDICase.

    A gap references its parent case + an evidence span (char-anchored).
    Gaps are immutable once created; updates create a new row and mark
    the old one as superseded.
    """

    __tablename__ = "cdi_documentation_gaps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_cases.id"), nullable=False, index=True,
    )

    # Gap classification (PDF §6.2 — 8 gap types)
    gap_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    """One of: diagnostic_specificity | etiology_unspecified | severity_unspecified
    | acuity_unspecified | anatomical_site_unspecified | clinical_correlation_unestablished
    | temporal_unspecified | conflicting_documentation"""

    description: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, default="", server_default="")
    minimal_clarification_needed: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Evidence binding (red line: chart_evidence_required)
    evidence_document_id: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_char_start: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_char_end: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_documented_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Workflow
    priority: Mapped[str] = mapped_column(
        String(16), default="routine", server_default="routine",
    )
    """routine | urgent"""
    status: Mapped[str] = mapped_column(
        String(32), default="OPEN", server_default="OPEN", index=True,
    )
    """OPEN | QUERY_DRAFTED | QUERY_SENT | RESOLVED | WONT_RESOLVE | SUPERSEDED"""

    # ICD-10-CN context (optional, for coding_specificity gap_type)
    candidate_codes: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")

    # Audit
    superseded_by_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Provider Query (Section 3)
# ---------------------------------------------------------------------------


class ProviderQueryModel(Base, TimestampMixin):
    """One row per Non-leading Provider Query generated for a gap.

    Lifecycle (PDF §7):
        DRAFT → PENDING_CDI_REVIEW → APPROVED → SENT_TO_CLINICIAN → VIEWED
        → RESPONDED → DOCUMENTATION_UPDATED → REVALIDATED → CLOSED

    Side states: CANCELLED | ESCALATED | EXPIRED

    SLA: routine=72h, urgent=24h (Gate 8 enforces)
    """

    __tablename__ = "cdi_provider_queries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_cases.id"), nullable=False, index=True,
    )
    gap_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_documentation_gaps.id"), nullable=False, index=True,
    )

    # Query content
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_options: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")

    # Evidence binding (mirrors gap; query may cite different quote than gap)
    evidence_document_id: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_char_start: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_char_end: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    evidence_spans: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]",
    )

    # Non-leading gate result (per query)
    nlq_gate_verdict: Mapped[str] = mapped_column(
        String(16), default="PENDING", server_default="PENDING",
    )
    """PASS | BLOCK | PENDING"""
    nlq_gate_rules_evaluated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nlq_gate_rules_passed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nlq_gate_block_reasons: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    nlq_gate_version: Mapped[str] = mapped_column(
        String(32), default="NLQ-001..009", server_default="NLQ-001..009",
    )

    # Lifecycle
    lifecycle_state: Mapped[str] = mapped_column(
        String(32), default="DRAFT", server_default="DRAFT", index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(16), default="routine", server_default="routine",
    )

    # SLA tracking (Gate 8)
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Reviewers / recipients
    cdi_specialist_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cdi_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clinician_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Audit
    created_by_agent_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


# ---------------------------------------------------------------------------
# Clinician Response
# ---------------------------------------------------------------------------


class ClinicianResponseModel(Base, TimestampMixin):
    """One row per clinician response to a Provider Query.

    A query may receive multiple responses over time (e.g. initial
    response, then update after chart review). The latest response
    drives DOCUMENTATION_UPDATED transition.
    """

    __tablename__ = "cdi_clinician_responses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    query_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_provider_queries.id"), nullable=False, index=True,
    )
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_cases.id"), nullable=False, index=True,
    )

    # Response content
    selected_option: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    free_text_response: Mapped[str] = mapped_column(Text, default="", server_default="")
    response_metadata: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")

    # Whether this response is the latest (for fast lookup)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", index=True)

    # Audit
    clinician_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Document Version (snapshot before/after clarification)
# ---------------------------------------------------------------------------


class DocumentVersionModel(Base, TimestampMixin):
    """Snapshot of a chart document at a point in time.

    Captured before CDI run (initial state) and after DOCUMENTATION_UPDATED
    (post-clarification state). Allows before/after diff view (Gate 7 UI).
    """

    __tablename__ = "cdi_document_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cdi_cases.id"), nullable=False, index=True,
    )
    query_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("cdi_provider_queries.id"), nullable=True, index=True,
    )

    # Document identification
    document_id: Mapped[str] = mapped_column(String(256), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(48), default="progress_note", server_default="progress_note",
    )
    """admission_note | progress_note | discharge_summary | lab_report | imaging_report | other"""

    # Snapshot
    version_label: Mapped[str] = mapped_column(
        String(32), default="initial", server_default="initial",
    )
    """initial | post_clarification | revalidated"""
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Diff summary (per Gate 7 UI)
    diff_summary: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    """e.g. {'added_sections': ['病原体'], 'modified_spans': [{'start': 234, 'end': 260, 'old': '肺炎', 'new': '肺炎链球菌性肺炎'}]}"""

    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


# ---------------------------------------------------------------------------
# Notification subscription
# ---------------------------------------------------------------------------


class CDINotificationSubscriptionModel(Base):
    """Tenant-scoped durable CDI notification routing configuration.

    Webhook shared secrets are stored only as versioned ciphertext.  The API
    refuses webhook registration when the PHI/envelope encryption key is not
    configured, so a development fallback can never persist the secret in
    plaintext.
    """

    __tablename__ = "cdi_notification_subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    user_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    channel: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1", index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(),
    )


__all__ = [
    "CDICaseModel",
    "DocumentationGapModel",
    "ProviderQueryModel",
    "ClinicianResponseModel",
    "DocumentVersionModel",
    "CDINotificationSubscriptionModel",
]
