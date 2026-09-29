from datetime import datetime,timezone
import uuid
from sqlalchemy import Column,String,Integer,DateTime,JSON,ForeignKey,UniqueConstraint,ForeignKeyConstraint
from app.database import Base
from app.services.phi_encryption import EncryptedPHIJSON

def uid():return str(uuid.uuid4())
def now():return datetime.now(timezone.utc)

class EvaluationDataset(Base):
    __tablename__='evaluation_datasets'
    __table_args__=(UniqueConstraint('organization_id','dataset_id','version'),)
    id=Column(String(36),primary_key=True,default=uid)
    organization_id=Column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    dataset_id=Column(String(36),nullable=False,index=True)
    version=Column(Integer,nullable=False)
    name=Column(String(120),nullable=False)
    split=Column(String(16),nullable=False)
    cases=Column(EncryptedPHIJSON,nullable=False)
    digest=Column(String(64),nullable=False)
    case_count=Column(Integer,nullable=False)
    review_status=Column(String(16),nullable=False,default='pending')
    reviews=Column(JSON,nullable=False,default=list)
    created_by=Column(String(128),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)

class EvaluationBatch(Base):
    __tablename__='evaluation_batches'
    __table_args__=(UniqueConstraint('organization_id','created_by','request_id'),ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id']))
    id=Column(String(36),primary_key=True,default=uid)
    organization_id=Column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    agent_id=Column(String(128),nullable=False)
    dataset_revision_id=Column(String(36),ForeignKey('evaluation_datasets.id'),nullable=False)
    draft_digest=Column(String(64),nullable=False)
    purpose=Column(String(32),nullable=False)
    request_id=Column(String(80),nullable=False)
    created_by=Column(String(128),nullable=False)
    state=Column(String(16),nullable=False,default='active')
    created_at=Column(DateTime(timezone=True),nullable=False,default=now)

class EvaluationBatchItem(Base):
    __tablename__='evaluation_batch_items'
    __table_args__=(UniqueConstraint('batch_id','case_index'),)
    id=Column(String(36),primary_key=True,default=uid)
    organization_id=Column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    batch_id=Column(String(36),ForeignKey('evaluation_batches.id'),nullable=False,index=True)
    case_index=Column(Integer,nullable=False)
    case_id=Column(String(80),nullable=False)
    state=Column(String(16),nullable=False,default='queued',index=True)
    claim_token=Column(String(36),nullable=True)
    lease_until=Column(DateTime(timezone=True),nullable=True)
    result=Column(JSON,nullable=True)
    error_code=Column(String(80),nullable=True)
    attempts=Column(JSON,nullable=False,default=list)
