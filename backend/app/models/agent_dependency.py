"""Tenant registry of operator-verified external dependency revisions."""
from datetime import datetime,timezone
import uuid
from sqlalchemy import Boolean,DateTime,ForeignKey,Index,String,UniqueConstraint,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
class AgentDependency(Base):
    __tablename__='agent_dependencies'
    __table_args__=(UniqueConstraint('organization_id','kind','name','version',name='uq_dependency_revision'),
        Index('uq_dependency_current','organization_id','kind','name',unique=True,postgresql_where=text('is_current'),sqlite_where=text('is_current=1')))
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    organization_id:Mapped[str]=mapped_column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    kind:Mapped[str]=mapped_column(String(16),nullable=False)
    name:Mapped[str]=mapped_column(String(100),nullable=False)
    version:Mapped[str]=mapped_column(String(100),nullable=False)
    artifact_digest:Mapped[str | None]=mapped_column(String(64),nullable=True)
    is_current:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    created_by:Mapped[str]=mapped_column(String(128),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),nullable=False)
