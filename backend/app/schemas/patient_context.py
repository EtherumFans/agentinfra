# iCoDer A1C.3 — Patient Context Pydantic schemas
"""Pydantic models for /api/v1/patient-context endpoints.

Mirrors PATIENT_CONTEXT_SCHEMA.json (A1C.3 contract).
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


VISIT_TYPES = Literal[
    "inpatient", "outpatient", "emergency", "day-case",
    "home-care", "telemed", "rehab", "observation",
]
PURPOSE_OF_USE = Literal[
    "treatment", "billing", "operations", "quality", "research", "public-health",
]
CONSENT_LEGAL_BASIS = Literal[
    "patient-consent", "treatment-necessity",
    "legal-obligation", "vital-interest", "public-interest",
]


class PatientContextCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    source_system: str = Field(..., min_length=1, max_length=64)
    patient_id: str = Field(..., min_length=1, max_length=64)
    encounter_id: Optional[str] = Field(None, max_length=64)
    visit_type: VISIT_TYPES
    department_id: str = Field(..., min_length=1, max_length=64)
    ward_id: Optional[str] = Field(None, max_length=64)
    clinician_id: str = Field(..., min_length=1, max_length=64)
    document_ids: list[str] = Field(default_factory=list)
    purpose_of_use: PURPOSE_OF_USE
    consent_legal_basis: CONSENT_LEGAL_BASIS
    trace_id: Optional[str] = Field(None, max_length=64)

    @field_validator("ward_id")
    @classmethod
    def _ward_required_for_inpatient(cls, v, info):
        visit = info.data.get("visit_type")
        if visit in ("inpatient", "day-case") and not v:
            raise ValueError(f"ward_id required for visit_type={visit}")
        return v

    @field_validator("consent_legal_basis")
    @classmethod
    def _research_requires_explicit_consent(cls, v, info):
        purpose = info.data.get("purpose_of_use")
        if purpose == "research" and v != "patient-consent":
            raise ValueError(
                f"purpose_of_use=research requires explicit consent_legal_basis=patient-consent"
            )
        return v


class PatientContextExtend(BaseModel):
    extend_seconds: int = Field(..., ge=60, le=86400,
                                 description="Additional seconds; total lifetime capped at 24h")


class PatientContextResponse(BaseModel):
    id: str
    organization_id: str
    tenant_id: str
    source_system: str
    patient_id: str
    encounter_id: Optional[str] = None
    visit_type: str
    department_id: str
    ward_id: Optional[str] = None
    clinician_id: str
    document_ids: list[str] = Field(default_factory=list)
    purpose_of_use: str
    consent_legal_basis: str
    trace_id: Optional[str] = None
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
