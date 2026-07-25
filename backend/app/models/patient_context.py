# iCoDer A1C.3 — Patient Context model
"""Closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT.

PatientContext is the iCoDer-side representation of an active HIS/EMR-side
patient treatment episode. It groups documents + coding runs + callbacks
under a single tenant-scoped entity with a hard 24h TTL.

Lifecycle:
  active → deleted (manual DELETE or 24h TTL cron)
  active → expired (24h TTL cron marks expired before deletion)

Distinguished from Encounter (which is the persistent medical-record
"visit" record). PatientContext is the short-lived HIS-integration bucket.
"""
from datetime import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


# PDF A1C.3 §七 enums
VISIT_TYPE_VALUES = (
    "inpatient", "outpatient", "emergency", "day-case",
    "home-care", "telemed", "rehab", "observation",
)
PURPOSE_OF_USE_VALUES = (
    "treatment", "billing", "operations", "quality", "research", "public-health",
)
CONSENT_LEGAL_BASIS_VALUES = (
    "patient-consent", "treatment-necessity",
    "legal-obligation", "vital-interest", "public-interest",
)
CONTEXT_STATUS_VALUES = ("active", "expired", "deleted")


class PatientContext(Base, TimestampMixin):
    __tablename__ = "patient_contexts"
    __table_args__ = (
        Index("ix_patient_contexts_org_patient", "organization_id", "patient_id"),
        Index("ix_patient_contexts_expires_at", "expires_at"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    encounter_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    visit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    department_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clinician_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    purpose_of_use: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_legal_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active", index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
