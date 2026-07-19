# iCoDer - Audit Log Model
from datetime import datetime
from typing import Optional
from sqlalchemy import String, JSON, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # encounter.create, review.generate, code.confirm, user.login, etc.
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)  # encounter, review, code, user
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # action-specific data
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")  # success, failure, warning
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Agent delegation audit (iter 3)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    agent_account_id: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    delegated_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # For LLM audit
    model_input_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_calls_made: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Phase A1A Gate 2 §2: tenancy classification ──────────────────
    # MODERN | LEGACY_TENANT_KNOWN | LEGACY_TENANT_UNKNOWN | QUARANTINED
    # See alembic 016.
    #
    # ── Phase A1A Gate 3.1 §3 — extended taxonomy ──
    # Plus MODERN_SYSTEM (intentional system-scope audit event, e.g.
    # api_client.authentication_rejected) and the three-way split of
    # LEGACY_TENANT_KNOWN into VERIFIED | INFERRED | AMBIGUOUS.
    # See alembic 017 + app.services.legacy_tenancy_attribution.
    tenancy_classification: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True,
    )

    # ── Phase A1A Gate 3.1 §4 — attribution provenance ──────────────
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
        comment="How many candidate orgs were considered.",
    )
