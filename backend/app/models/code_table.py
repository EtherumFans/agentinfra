# iCoDer — Multi-Code-Table Model
# Supports flexible code table management for different institutions
from sqlalchemy import JSON, String, Boolean, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class CodeTable(Base, TimestampMixin):
    """A coding dictionary (ICD-10-CN national, local hospital, insurance, etc.)"""
    __tablename__ = "code_tables"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    code_system: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(32), default="standard")
    institution: Mapped[str] = mapped_column(String(256), default="")
    total_codes: Mapped[int] = mapped_column(default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class CodeMapping(Base, TimestampMixin):
    """Maps codes between different CodeTables (e.g. hospital local → national standard)"""
    __tablename__ = "code_mappings"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    source_table_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    target_table_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_code: Mapped[str] = mapped_column(String(64), nullable=False)
    target_name: Mapped[str] = mapped_column(String(256), default="")
    confidence: Mapped[float] = mapped_column(default=1.0)
    mapping_type: Mapped[str] = mapped_column(String(32), default="exact")
