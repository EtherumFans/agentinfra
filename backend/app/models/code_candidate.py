# iCoDer - Code Candidate Model
from typing import Optional
from sqlalchemy import String, Float, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin

class CodeCandidate(Base, TimestampMixin):
    __tablename__ = "code_candidates"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    review_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("coding_reviews.id"), nullable=False, index=True
    )
    finding: Mapped[str] = mapped_column(String(512), nullable=False)
    code_system: Mapped[str] = mapped_column(String(64), nullable=False)  # ICD10_CN, ICD9_CM3, LOCAL
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    chapter: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    evidence_ids: Mapped[dict] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending, supported, unsupported, needs_review, rejected, confirmed
    rule_checks: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # [{rule_name, status: pass/warn/fail, message}]
    human_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # confirmed, rejected, modified
    human_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    modified_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    modified_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    review: Mapped["CodingReview"] = relationship("CodingReview", back_populates="candidates")
