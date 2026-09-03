"""Append-only integrity archive for audit events."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class AuditIntegrityArchive(Base, TimestampMixin):
    __tablename__ = "audit_integrity_archive"

    # Deliberately no FK: the governed hot-store retention job may delete an
    # AuditLog after its minimum retention window, while this archive proof
    # must survive independently.
    audit_log_id: Mapped[str] = mapped_column(
        String(12), nullable=False, unique=True, index=True,
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=True, index=True,
    )
    stream_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
