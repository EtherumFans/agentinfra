"""SQLAlchemy models for Context (SPEC §4.3).

Imported by alembic/env.py so Base.metadata picks them up for autogenerate.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContextRow(Base):
    __tablename__ = "contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_input_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    original_input_ref: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )

    messages: Mapped[list["ContextMessageRow"]] = relationship(
        back_populates="context",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[list["ContextTaskRefRow"]] = relationship(
        back_populates="context",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    artifacts: Mapped[list["ContextArtifactRefRow"]] = relationship(
        back_populates="context",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_contexts_expires_at", "expires_at"),
        Index("idx_contexts_agent_id", "agent_id"),
        Index("idx_contexts_status", "status"),
    )


class ContextMessageRow(Base):
    __tablename__ = "context_messages"
    __table_args__ = (
        Index(
            "fk_context_messages_context_id",
            "context_id",
        ),
    )

    context_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    parts_json: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )

    context: Mapped[ContextRow] = relationship(back_populates="messages")


class ContextTaskRefRow(Base):
    __tablename__ = "context_task_refs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('submitted', 'working', 'completed', 'failed', 'canceled')",
            name="ck_context_task_refs_state",
        ),
    )

    context_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    context: Mapped[ContextRow] = relationship(back_populates="tasks")


class ContextArtifactRefRow(Base):
    __tablename__ = "context_artifact_refs"

    context_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)

    context: Mapped[ContextRow] = relationship(back_populates="artifacts")


class OriginalInputAuditRow(Base):
    __tablename__ = "original_input_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(36), nullable=False)
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    retention_until: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_original_input_audit_context_id", "context_id"),
        Index("idx_original_input_audit_retention", "retention_until"),
    )