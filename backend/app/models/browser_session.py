"""Revocable browser sessions; credentials themselves are never stored."""
from datetime import datetime,timezone
from sqlalchemy import String,DateTime,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from app.database import Base
class BrowserSession(Base):
    __tablename__='browser_sessions'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id:Mapped[str]=mapped_column(String(36),ForeignKey('users.id',ondelete='CASCADE'),nullable=False,index=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revoked_at:Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
