"""Encrypted, tenant-scoped facts for the Corti-compatible Facts API."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicalFactRecord(Base):
    __tablename__ = "clinical_facts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "owner_id",
            "interaction_id",
            "fact_id",
            name="uq_clinical_fact_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    interaction_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    fact_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_key: Mapped[str] = mapped_column(String(96), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_discarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    encrypted_text: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
