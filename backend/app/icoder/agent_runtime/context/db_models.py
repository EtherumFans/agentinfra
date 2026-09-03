"""SQLAlchemy models for Context (SPEC §4.3).

Imported by alembic/env.py so Base.metadata picks them up for autogenerate.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    organization_id: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_input_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )
    original_input_ref: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=""
    )

    messages: Mapped[list["ContextMessageRow"]] = relationship(
        back_populates="context",
        foreign_keys="ContextMessageRow.context_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks: Mapped[list["ContextTaskRefRow"]] = relationship(
        back_populates="context",
        foreign_keys="ContextTaskRefRow.context_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    artifacts: Mapped[list["ContextArtifactRefRow"]] = relationship(
        back_populates="context",
        foreign_keys="ContextArtifactRefRow.context_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_contexts_org_id"),
        Index("idx_contexts_expires_at", "expires_at"),
        Index("idx_contexts_agent_id", "agent_id"),
        Index("idx_contexts_status", "status"),
        Index("idx_contexts_organization_id", "organization_id"),
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
    # Nullable in ORM-created local SQLite databases for legacy fixture
    # compatibility; revision 065 makes this NOT NULL in PostgreSQL.
    organization_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
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

    context: Mapped[ContextRow] = relationship(
        back_populates="messages", foreign_keys=[context_id]
    )


class ContextTaskRefRow(Base):
    __tablename__ = "context_task_refs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('submitted', 'working', 'completed', 'failed', 'canceled', "
            "'rejected', 'input-required', 'auth-required')",
            name="ck_context_task_refs_state",
        ),
        UniqueConstraint(
            "organization_id", "context_id", "task_id",
            name="uq_context_task_refs_org_context_task",
        ),
    )

    context_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    context: Mapped[ContextRow] = relationship(
        back_populates="tasks", foreign_keys=[context_id]
    )


class ContextArtifactRefRow(Base):
    __tablename__ = "context_artifact_refs"
    context_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contexts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)

    context: Mapped[ContextRow] = relationship(
        back_populates="artifacts", foreign_keys=[context_id]
    )


class A2ATaskExecutionRow(Base):
    """Durable, tenant-owned execution payload for asynchronous A2A Tasks.

    The request/result columns contain only route-redacted JSON and are
    encrypted by the service layer.  Lease fields make recovery safe for a
    single database-backed worker and provide an atomic boundary for future
    multi-worker deployments.
    """

    __tablename__ = "a2a_task_executions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "agent_id",
            "message_id",
            name="uq_a2a_task_execution_org_agent_message",
        ),
        Index("ix_a2a_task_execution_org_agent", "organization_id", "agent_id"),
        Index("ix_a2a_task_execution_lease", "lease_expires_at"),
    )

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    context_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contexts.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(String(12), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)


class A2ATaskEventRow(Base):
    """Append-only durable Task state event used by Subscribe resume."""

    __tablename__ = "a2a_task_events"
    __table_args__ = (
        Index("ix_a2a_task_event_task_sequence", "task_id", "sequence_id"),
        Index("ix_a2a_task_event_org_agent", "organization_id", "agent_id"),
    )

    sequence_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    context_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contexts.id", ondelete="CASCADE"), nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(String(12), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_append: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    artifact_last_chunk: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    artifact_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_payload_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    artifact_payload_size_bytes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)


class A2ATaskArtifactRow(Base):
    """Encrypted Artifact payload with unambiguous Context and Task ownership."""

    __tablename__ = "a2a_task_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_id", "task_id"],
            ["context_task_refs.context_id", "context_task_refs.task_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "context_id", "task_id", "artifact_id",
            name="uq_a2a_task_artifacts_org_context_task_artifact",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_a2a_task_artifact_size"),
        Index(
            "ix_a2a_task_artifact_task_created",
            "context_id",
            "task_id",
            "created_at",
        ),
    )

    context_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class A2AArtifactObjectRow(Base):
    """Encrypted file object held in quarantine until all scanners pass."""

    __tablename__ = "a2a_artifact_objects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["context_id", "task_id", "artifact_id"],
            [
                "a2a_task_artifacts.context_id",
                "a2a_task_artifacts.task_id",
                "a2a_task_artifacts.artifact_id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "object_id",
            name="uq_a2a_artifact_objects_org_object",
        ),
        CheckConstraint("size_bytes > 0", name="ck_a2a_artifact_object_size"),
        CheckConstraint(
            "status IN ('quarantined', 'available', 'rejected')",
            name="ck_a2a_artifact_object_status",
        ),
        CheckConstraint(
            "malware_scan_status IN ('pending', 'clean', 'infected', 'error')",
            name="ck_a2a_artifact_object_malware_status",
        ),
        CheckConstraint(
            "dlp_scan_status IN ('pending', 'clear', 'restricted', 'blocked', 'error')",
            name="ck_a2a_artifact_object_dlp_status",
        ),
        CheckConstraint(
            "data_classification IN ('deidentified', 'clinical-sensitive')",
            name="ck_a2a_artifact_object_classification",
        ),
        Index(
            "ix_a2a_artifact_object_owner",
            "organization_id",
            "context_id",
            "task_id",
            "artifact_id",
            "created_at",
        ),
        Index("ix_a2a_artifact_object_status", "status", "created_at"),
    )

    object_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(12), nullable=False)
    context_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    filename_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    declared_media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    detected_media_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_classification: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_ciphertext: Mapped[bytes | None] = mapped_column(nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    malware_scan_status: Mapped[str] = mapped_column(String(16), nullable=False)
    dlp_scan_status: Mapped[str] = mapped_column(String(16), nullable=False)
    scan_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    scanned_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class A2AArtifactDownloadGrantRow(Base):
    """Revocable, one-time authorization for one managed object download."""

    __tablename__ = "a2a_artifact_download_grants"
    __table_args__ = (
        CheckConstraint(
            "purpose_of_use IN ('treatment', 'payment', 'healthcare_operations')",
            name="ck_a2a_artifact_grant_purpose",
        ),
        Index("ix_a2a_artifact_grant_object_expiry", "object_id", "expires_at"),
        Index("ix_a2a_artifact_grant_expiry", "expires_at", "consumed_at"),
    )

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("a2a_artifact_objects.object_id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(String(12), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose_of_use: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OriginalInputAuditRow(Base):
    __tablename__ = "original_input_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    context_id: Mapped[str] = mapped_column(String(36), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    original_input: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    retention_until: Mapped[DateTime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_original_input_audit_context_id", "context_id"),
        Index("idx_original_input_audit_retention", "retention_until"),
    )
