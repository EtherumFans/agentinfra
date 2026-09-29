"""Organization-owned LLM credentials, never serialized by organization APIs."""
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ModelConnection(Base):
    __tablename__ = 'model_connections'
    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey('organizations.id'), primary_key=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
