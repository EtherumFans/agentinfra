import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from app.database import Base
from app.services.phi_encryption import EncryptedPHIJSON

class DocumentReview(Base):
    __tablename__='document_reviews'
    __table_args__=(UniqueConstraint('organization_id','created_by','request_id'),)
    id=Column(String(36),primary_key=True,default=lambda:str(uuid.uuid4()))
    organization_id=Column(String(12),ForeignKey('organizations.id'),nullable=False,index=True)
    created_by=Column(String(128),nullable=False)
    request_id=Column(String(80),nullable=False)
    version=Column(Integer,nullable=False,default=1)
    status=Column(String(16),nullable=False,default='pending')
    content=Column(EncryptedPHIJSON(),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
