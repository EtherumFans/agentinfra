"""Durable agent execution and notification outbox in a single transaction."""
from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
class AgentJob(Base):
    __tablename__='agent_jobs'
    __table_args__=(ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id'],ondelete='CASCADE'),
        UniqueConstraint('organization_id','actor_kind','actor_id','idempotency_key',name='uq_agent_job_request'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    organization_id: Mapped[str]=mapped_column(String(12),nullable=False,index=True)
    agent_id: Mapped[str]=mapped_column(String(128),nullable=False)
    actor_kind: Mapped[str]=mapped_column(String(12),nullable=False)
    actor_id: Mapped[str]=mapped_column(String(128),nullable=False)
    idempotency_key: Mapped[str]=mapped_column(String(150),nullable=False)
    request_digest: Mapped[str]=mapped_column(String(64),nullable=False)
    version: Mapped[str]=mapped_column(String(64),nullable=False)
    payload: Mapped[str]=mapped_column(Text,nullable=False)
    result: Mapped[str | None]=mapped_column(Text,nullable=True)
    run_id: Mapped[str | None]=mapped_column(String(64),nullable=True)
    state: Mapped[str]=mapped_column(String(32),default='queued',nullable=False,index=True)
    error_code: Mapped[str | None]=mapped_column(String(80),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
    finished_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    lease_until: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    callback_url: Mapped[str | None]=mapped_column(Text,nullable=True)
    notification_state: Mapped[str]=mapped_column(String(20),default='none',nullable=False)
    notification_attempts: Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    notification_due: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    notification_lease: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
