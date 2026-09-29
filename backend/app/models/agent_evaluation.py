"""Immutable tenant-scoped evaluation reports; no raw sample content stored."""
from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, ForeignKeyConstraint, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AgentEvaluation(Base):
    __tablename__='agent_evaluations'
    __table_args__=(ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id'],ondelete='CASCADE'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    organization_id: Mapped[str]=mapped_column(String(12),nullable=False,index=True)
    agent_id: Mapped[str]=mapped_column(String(128),nullable=False)
    report: Mapped[dict]=mapped_column(JSON,nullable=False)
    created_by: Mapped[str]=mapped_column(String(128),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
