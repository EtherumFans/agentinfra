# iCoDer — Gold Case Model (Phase 10 extended)
from typing import Optional
from sqlalchemy import String, JSON, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class GoldCase(Base, TimestampMixin):
    __tablename__ = "gold_cases"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    case_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    department: Mapped[str] = mapped_column(String(128), nullable=False)
    diagnosis_group: Mapped[str] = mapped_column(String(128), nullable=False)

    # Original codes (before review)
    original_primary_diagnosis: Mapped[str] = mapped_column(String(32), default="")
    original_primary_diag_name: Mapped[str] = mapped_column(String(256), default="")
    original_main_procedure: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    original_main_proc_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Expected gold standard codes
    expected_principal_diagnosis: Mapped[str] = mapped_column(String(32), default="")
    expected_principal_diag_name: Mapped[str] = mapped_column(String(256), default="")
    expected_principal_procedure: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    expected_principal_proc_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    expected_secondary_diagnoses: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_procedure_codes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expected_drg_group: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Acceptable alternatives
    acceptable_alternatives: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Reasoning expectations
    reasoning_expectations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Issue lists
    missing_codes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    unsupported_codes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    documentation_gaps: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Evidence
    evidence_spans: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    full_case_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Metadata
    difficulty: Mapped[str] = mapped_column(String(32), default="medium")
    specialty: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    risk_tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")

    # Review
    reviewer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    review_time: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Evaluation stats
    agent_accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_evaluated_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
