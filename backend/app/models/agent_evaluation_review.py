"""Append-only review decisions, separate from immutable evaluation reports."""
from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AgentEvaluationReview(Base):
    __tablename__ = 'agent_evaluation_reviews'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    evaluation_id: Mapped[str] = mapped_column(String(36),ForeignKey('agent_evaluations.id'),nullable=False,index=True)
    decision: Mapped[str] = mapped_column(String(16),nullable=False)
    note: Mapped[str] = mapped_column(Text,nullable=False)
    created_by: Mapped[str] = mapped_column(String(128),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
