# iCoDer - Conversation Memory Model
from datetime import datetime

from sqlalchemy import String, Text, Float, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class MemoryConsent(Base, TimestampMixin):
    """Revocable, user-owned authority for one Agent's persistent memory."""

    __tablename__ = "memory_consents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", "agent_id", "purpose_of_use",
            name="uq_memory_consent_subject_agent_purpose",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("users.id"), nullable=False, index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("agents.id"), nullable=False, index=True,
    )
    purpose_of_use: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, default="user-consent",
        server_default="user-consent",
    )
    retention_days: Mapped[int] = mapped_column(
        nullable=False,
        default=30,
        server_default="30",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[str] = mapped_column(String(12), nullable=False)


class ConversationMemory(Base, TimestampMixin):
    __tablename__ = "conversation_memories"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False, index=True)
    expert_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("experts.id"), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("agents.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM-generated summary
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1 relevance score
    key_facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: extracted key facts
    # Governed persistent Connector metadata. Legacy rows intentionally keep
    # these fields NULL and are therefore invisible to governed recall.
    consent_id: Mapped[str | None] = mapped_column(
        String(12), ForeignKey(
            "memory_consents.id", name="fk_conversation_memories_consent_id",
        ), nullable=True, index=True,
    )
    actor_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purpose_of_use: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    content_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
