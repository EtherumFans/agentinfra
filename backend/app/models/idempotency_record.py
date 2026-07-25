"""SQLAlchemy model for idempotency_records (Phase 7 Gate 3).

Mirrors alembic 012. Used by app.services.idempotency_service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyRecord(Base):
    """Server-side dedup record for partner API runs.

    Per Phase 7 §8.1 schema. The (organization_id, api_client_id,
    idempotency_key) tuple is UNIQUE — enforced both at the DB layer
    (alembic 012 uq_idempotency_org_client_key) and via INSERT-then-
    on-conflict handling in IdempotencyService.
    """

    __tablename__ = "idempotency_records"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "api_client_id",
            "idempotency_key",
            name="uq_idempotency_org_client_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12),
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    api_client_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    context_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="pending",
    )
    response_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, server_default=func.current_timestamp(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<IdempotencyRecord id={self.id} "
            f"key={self.idempotency_key[:8]}... "
            f"status={self.status} run_id={self.run_id}>"
        )
