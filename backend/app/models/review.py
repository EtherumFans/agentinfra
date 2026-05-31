# iCoDer - Coding Review Model
import enum
from typing import Optional
from sqlalchemy import String, Float, JSON, ForeignKey, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin

class ReviewJudgment(str, enum.Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    CONFIRMED = "confirmed"

class CodingReview(Base, TimestampMixin):
    __tablename__ = "coding_reviews"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    review_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    encounter_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("encounters.id"), nullable=False, index=True
    )
    agent_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    model_used: Mapped[str] = mapped_column(String(64), default="")

    # Primary Diagnosis
    primary_diagnosis_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    primary_diagnosis_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    primary_diagnosis_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    primary_diagnosis_evidence_ids: Mapped[dict] = mapped_column(JSON, default=list)
    primary_diagnosis_judgment: Mapped[ReviewJudgment] = mapped_column(
        Enum(ReviewJudgment), default=ReviewJudgment.NEEDS_REVIEW
    )
    primary_diagnosis_reasoning: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Main Procedure
    main_procedure_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    main_procedure_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    main_procedure_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    main_procedure_evidence_ids: Mapped[dict] = mapped_column(JSON, default=list)
    main_procedure_judgment: Mapped[ReviewJudgment] = mapped_column(
        Enum(ReviewJudgment), default=ReviewJudgment.NEEDS_REVIEW
    )

    # Secondary Diagnoses
    secondary_diagnoses: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # list of code objects
    # Other Procedures
    other_procedures: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Analysis Results
    diagnosis_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    procedure_analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    documentation_gaps: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    uncodable_items: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    drg_impact: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    human_checklist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    validation_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Full Report
    report_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human Review
    human_review_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending, in_review, completed, appealed
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Evidence Ranking & Confidence Calibration (persisted for audit)
    evidence_ranking: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence_calibration: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Processing
    processing_time_ms: Mapped[Optional[int]] = mapped_column(default=None)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0)

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="reviews")
    evidences: Mapped[list["ClinicalEvidence"]] = relationship(
        "ClinicalEvidence", back_populates="review", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["CodeCandidate"]] = relationship(
        "CodeCandidate", back_populates="review", cascade="all, delete-orphan"
    )
