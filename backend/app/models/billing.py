# iCoDer - Billing Models
from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # credit / debit
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String(256), default="")
    source: Mapped[str] = mapped_column(String(64), default="")  # purchase / api_usage / refund
