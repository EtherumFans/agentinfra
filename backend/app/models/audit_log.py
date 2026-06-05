# iCoDer - Audit Log Model
from typing import Optional
from sqlalchemy import String, JSON, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin

class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # encounter.create, review.generate, code.confirm, user.login, etc.
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)  # encounter, review, code, user
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # action-specific data
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")  # success, failure, warning
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Agent delegation audit (iter 3)
    agent_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    agent_account_id: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    delegated_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # For LLM audit
    model_input_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_output_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_calls_made: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
