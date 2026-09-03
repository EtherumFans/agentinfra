"""Development Agent Run preauthorization and settlement state."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class BillingRunSettlement(Base, TimestampMixin):
    """One idempotent local-ledger settlement per Agent Run."""

    __tablename__ = "billing_run_settlements"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "run_id", name="uq_billing_run_settlement_org_run"
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("users.id"), nullable=False, index=True,
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="RESERVED", server_default="RESERVED",
        index=True,
    )
    reserved_amount: Mapped[float] = mapped_column(Float, nullable=False)
    settled_amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0",
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CNY", server_default="CNY",
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


__all__ = ["BillingRunSettlement"]
