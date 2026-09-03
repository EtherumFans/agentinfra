"""Encrypted, tenant-scoped generated documents."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GuidedDocumentRecord(Base):
    __tablename__ = "guided_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "owner_id", "document_id",
            name="uq_guided_document_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_string_document_json: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_structured_document_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_labels_json: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_classic_sections_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_consumed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class GuidedSectionRecord(Base):
    __tablename__ = "guided_sections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "section_id", name="uq_guided_section_scope"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_definition_json: Mapped[str] = mapped_column(Text, nullable=False)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="project")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
