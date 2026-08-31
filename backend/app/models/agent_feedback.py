"""Tenant-scoped, caller-owned feedback for Agentic v2 Tasks."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgentTaskFeedback(Base):
    __tablename__ = "agent_task_feedback"
    __table_args__ = (
        CheckConstraint("rating_scale = 'binary'", name="ck_agent_feedback_scale"),
        CheckConstraint("rating_value IN (0, 1)", name="ck_agent_feedback_value"),
        UniqueConstraint(
            "organization_id",
            "context_id",
            "task_id",
            "target_key",
            "actor_type",
            "actor_id",
            name="uq_agent_feedback_actor_target",
        ),
        Index(
            "ix_agent_feedback_org_context_task_actor",
            "organization_id",
            "context_id",
            "task_id",
            "actor_type",
            "actor_id",
        ),
        Index("ix_agent_feedback_retention", "retention_until"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    context_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contexts.id", ondelete="CASCADE"), nullable=False,
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_key: Mapped[str] = mapped_column(String(72), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rating_scale: Mapped[str] = mapped_column(
        String(16), nullable=False, default="binary", server_default="binary",
    )
    rating_value: Mapped[int] = mapped_column(Integer, nullable=False)
    labels_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    reason_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason_redacted: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="0",
    )
    safe_metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeedbackTrainingAuthorization(Base):
    """Independent, owner-approved eligibility for one feedback snapshot.

    This row is deliberately not a training export and never stores Task,
    Message, prompt, output, or decrypted feedback reason content.  Consumers
    must additionally verify ``status``, ``expires_at`` and
    ``feedback_digest`` before treating the feedback metadata as eligible for
    the narrow quality-improvement purpose.
    """

    __tablename__ = "feedback_training_authorizations"
    __table_args__ = (
        CheckConstraint(
            "purpose_of_use = 'quality_improvement'",
            name="ck_feedback_training_purpose",
        ),
        CheckConstraint(
            "data_scope = 'feedback_metadata_only'",
            name="ck_feedback_training_data_scope",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_feedback_training_status",
        ),
        UniqueConstraint(
            "organization_id",
            "feedback_id",
            name="uq_feedback_training_org_feedback",
        ),
        Index(
            "ix_feedback_training_org_context_task_status",
            "organization_id",
            "context_id",
            "task_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    context_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_task_feedback.id", ondelete="CASCADE"),
        nullable=False,
    )
    purpose_of_use: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quality_improvement",
        server_default="quality_improvement",
    )
    data_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="feedback_metadata_only",
        server_default="feedback_metadata_only",
    )
    feedback_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authorized_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


__all__ = ["AgentTaskFeedback", "FeedbackTrainingAuthorization"]
