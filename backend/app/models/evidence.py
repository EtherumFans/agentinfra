# iCoDer - Clinical Evidence Model
from typing import Optional
from sqlalchemy import String, Float, Boolean, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin
from app.services.phi_encryption import EncryptedPHIText

class ClinicalEvidence(Base, TimestampMixin):
    __tablename__ = "clinical_evidences"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=False, index=True)
    review_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("coding_reviews.id"), nullable=False, index=True
    )
    doc_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("documents.id"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(EncryptedPHIText(), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # diagnosis_evidence, procedure_evidence, negation, anatomy, etiology, timing
    supports_codes: Mapped[dict] = mapped_column(JSON, default=list)  # list of code strings
    certainty: Mapped[str] = mapped_column(String(32), default="suspected")
    # confirmed, probable, suspected, ruled_out
    negation: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    start_char: Mapped[Optional[int]] = mapped_column(default=None)
    end_char: Mapped[Optional[int]] = mapped_column(default=None)

    review: Mapped["CodingReview"] = relationship("CodingReview", back_populates="evidences")
