"""HIS/EMR patient-context lifecycle with idempotent creation."""

from __future__ import annotations

from typing import Literal, TypedDict
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


VisitType = Literal[
    "inpatient", "outpatient", "emergency", "day-case", "home-care",
    "telemed", "rehab", "observation",
]
PurposeOfUse = Literal[
    "treatment", "billing", "operations", "quality", "research", "public-health",
]
ConsentLegalBasis = Literal[
    "patient-consent", "treatment-necessity", "legal-obligation",
    "vital-interest", "public-interest",
]


class PatientContextRequired(TypedDict):
    tenant_id: str
    source_system: str
    patient_id: str
    visit_type: VisitType
    department_id: str
    clinician_id: str
    purpose_of_use: PurposeOfUse
    consent_legal_basis: ConsentLegalBasis


class PatientContextCreate(PatientContextRequired, total=False):
    encounter_id: str | None
    ward_id: str | None
    document_ids: list[str]
    trace_id: str | None


class PatientContextResponse(PatientContextRequired):
    id: str
    organization_id: str
    encounter_id: str | None
    ward_id: str | None
    document_ids: list[str]
    trace_id: str | None
    status: Literal["active", "expired", "deleted"]
    expires_at: str
    created_at: str
    updated_at: str


class PatientContextResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def create(
        self,
        body: PatientContextCreate,
        *,
        idempotency_key: str | None = None,
        request_options: RequestOptions | None = None,
    ) -> PatientContextResponse:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = self._client.post(
            "/api/v1/patient-context",
            json=body,
            headers=headers,
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def get(
        self,
        context_id: str,
        request_options: RequestOptions | None = None,
    ) -> PatientContextResponse:
        response = self._client.get(
            f"/api/v1/patient-context/{quote(context_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def delete(
        self,
        context_id: str,
        request_options: RequestOptions | None = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v1/patient-context/{quote(context_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()

    def extend(
        self,
        context_id: str,
        extend_seconds: int,
        request_options: RequestOptions | None = None,
    ) -> PatientContextResponse:
        if (
            not isinstance(extend_seconds, int)
            or isinstance(extend_seconds, bool)
            or extend_seconds < 60
            or extend_seconds > 86400
        ):
            raise ValueError("extend_seconds must be an integer between 60 and 86400")
        response = self._client.post(
            f"/api/v1/patient-context/{quote(context_id, safe='')}/extend",
            json={"extend_seconds": extend_seconds},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()
