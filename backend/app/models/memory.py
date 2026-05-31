# iCoDer - Conversation Memory Model
from sqlalchemy import String, Text, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class ConversationMemory(Base, TimestampMixin):
    __tablename__ = "conversation_memories"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False, index=True)
    expert_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("experts.id"), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("agents.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM-generated summary
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1 relevance score
    key_facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: extracted key facts
