# iCoDer - Encounter & Document Models
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin

class Encounter(Base, TimestampMixin):
    __tablename__ = "encounters"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    encounter_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 脱敏
    department: Mapped[str] = mapped_column(String(128), nullable=False)
    admission_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    discharge_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    admission_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 主诉
    discharge_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    existing_diagnosis_codes: Mapped[dict] = mapped_column(JSON, default=list)  # [{code, name}]
    existing_procedure_codes: Mapped[dict] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, reviewing, completed, archived
    submitted_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="encounter", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["CodingReview"]] = relationship(
        "CodingReview", back_populates="encounter", cascade="all, delete-orphan"
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    encounter_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("encounters.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 入院记录, 出院记录, 手术记录, 检查报告, 病程记录, 会诊记录, MRI_report, CT_report, etc.
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_order: Mapped[int] = mapped_column(default=0)

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="documents")
