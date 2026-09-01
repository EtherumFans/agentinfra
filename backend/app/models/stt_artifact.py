"""Durable, tenant-scoped artifacts for Corti-compatible STT APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class STTInteraction(Base):
    __tablename__ = "stt_interactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_stt_interactions_organization",
        ),
        UniqueConstraint(
            "organization_id", "owner_id", "interaction_id",
            name="uq_stt_interaction_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class STTRecording(Base):
    __tablename__ = "stt_recordings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_interactions.organization_id",
                "stt_interactions.owner_id",
                "stt_interactions.interaction_id",
            ],
            name="fk_stt_recordings_interaction_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "owner_id", "interaction_id", "recording_id",
            name="uq_stt_recording_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    recording_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class STTTranscript(Base):
    __tablename__ = "stt_transcripts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_interactions.organization_id",
                "stt_interactions.owner_id",
                "stt_interactions.interaction_id",
            ],
            name="fk_stt_transcripts_interaction_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "owner_id", "interaction_id", "transcript_id",
            name="uq_stt_transcript_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    transcript_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recording_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    encrypted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    participant_roles_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class STTStreamLease(Base):
    """Cross-process ownership fence for one active Streams interaction."""

    __tablename__ = "stt_stream_leases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_interactions.organization_id",
                "stt_interactions.owner_id",
                "stt_interactions.interaction_id",
            ],
            name="fk_stt_stream_leases_interaction_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("session_id", name="uq_stt_stream_lease_session"),
        Index("ix_stt_stream_lease_expiry", "lease_expires_at"),
    )

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class STTStreamCheckpoint(Base):
    """Encrypted resumable state for one retained, unfinished Stream."""

    __tablename__ = "stt_stream_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_interactions.organization_id",
                "stt_interactions.owner_id",
                "stt_interactions.interaction_id",
            ],
            name="fk_stt_stream_checkpoints_interaction_scope",
            ondelete="CASCADE",
        ),
        Index("ix_stt_stream_checkpoint_updated", "updated_at"),
    )

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(240), nullable=False)
    encrypted_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    state_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    audio_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class STTStreamCheckpointChunk(Base):
    """Append-only encrypted audio chunk owned by a Stream checkpoint."""

    __tablename__ = "stt_stream_checkpoint_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_stream_checkpoints.organization_id",
                "stt_stream_checkpoints.owner_id",
                "stt_stream_checkpoints.interaction_id",
            ],
            name="fk_stt_stream_checkpoint_chunk_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_stt_stream_checkpoint_chunk_scope",
            "organization_id",
            "owner_id",
            "interaction_id",
        ),
    )

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interaction_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
