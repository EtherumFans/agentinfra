"""iCoDer ``GET /api/v2/tools/interactions/{id}/documents/`` — Corti §13.4 Documents Classic.

Cycle 5 (2026-07-01) — wire-shape parity for the legacy Documents Classic
LIST endpoint. The Corti docs tag this family as "Documents (Classic)"
with a "Planned deprecation" notice; the iCoDer backend mirrors that
framing by shipping the LIST endpoint with stub data only.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/documents-classic-list.md`` (7,235
  bytes, fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/documents-classic/list-documents.md``).
  Path: ``GET /interactions/{id}/documents/`` → operationId
  ``documents_list``.

What this endpoint IS
---------------------
- A read-only LIST endpoint returning the legacy Corti Documents Classic
  envelope ``{data: [...]}`` for a single interaction.

What this endpoint is NOT
--------------------------
- NOT a CRUD surface. Cycle 5 ships stub data only (2 hand-crafted
  document responses). Real document storage design is a separate
  Phase 2 task — until then the iCoDer Cycles 3+4 endpoints do not
  persist documents, so this LIST is intentionally empty-feeling.
- NOT a deprecation-banner surface. Banners are a Phase 1.5+ frontend
  concern; the backend wire contract here matches the live Corti
  envelope 1:1, including the lack of a deprecation marker in the
  response body.

Filter / scope behavior
-----------------------
The Corti spec scopes the LIST to a single ``{id}`` (the interaction
UUID). No other query params are accepted in Cycle 5 — the captured
spec declares only the path param + ``Tenant-Name`` header.

Stub data: 2 documents (one SOAP-style discharge summary + one
outpatient note), one of which has ``isStream=true`` to exercise that
field.
"""

from __future__ import annotations

import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.v2_tools_documents_classic import (
    CommonUsageInfo,
    DocumentsGetResponse,
    DocumentsListResponse,
    DocumentsSection,
)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Stub data (Cycle 5; replaced by real storage in a later cycle) ──


def _stub_documents_for_interaction(interaction_id: str) -> List[DocumentsGetResponse]:
    """Deterministic stub data per interaction UUID.

    The interaction UUID is echoed into the document IDs so SDK callers
    can verify the path-scoping contract: same ``{id}`` ⇒ same stub
    data, different ``{id}`` ⇒ different stub data.
    """
    return [
        DocumentsGetResponse(
            id=f"{interaction_id}-0001",
            name="Discharge Summary",
            templateRef="discharge-summary-v1",
            isStream=False,
            sections=[
                DocumentsSection(
                    key="subjective",
                    name="Subjective",
                    text="Patient reports improving dyspnea on exertion.",
                    sort=0,
                    createdAt="2026-06-01T08:00:00Z",
                    updatedAt="2026-06-01T08:05:00Z",
                ),
                DocumentsSection(
                    key="objective",
                    name="Objective",
                    text="BP 130/82, HR 76, SpO2 96% on room air.",
                    sort=1,
                    createdAt="2026-06-01T08:00:00Z",
                    updatedAt="2026-06-01T08:05:00Z",
                ),
                DocumentsSection(
                    key="assessment",
                    name="Assessment",
                    text="CHF NYHA Class II, improving.",
                    sort=2,
                    createdAt="2026-06-01T08:00:00Z",
                    updatedAt="2026-06-01T08:05:00Z",
                ),
                DocumentsSection(
                    key="plan",
                    name="Plan",
                    text="Continue ACE inhibitor; follow-up in 2 weeks.",
                    sort=3,
                    createdAt="2026-06-01T08:00:00Z",
                    updatedAt="2026-06-01T08:05:00Z",
                ),
            ],
            createdAt="2026-06-01T08:00:00Z",
            updatedAt="2026-06-01T08:05:00Z",
            outputLanguage="en-US",
            usageInfo=CommonUsageInfo(creditsConsumed=0.012),
        ),
        DocumentsGetResponse(
            id=f"{interaction_id}-0002",
            name="Outpatient Note (Streamed)",
            templateRef="outpatient-note-v2",
            isStream=True,
            sections=[
                DocumentsSection(
                    key="history",
                    name="History",
                    text="67yo M c/o chest tightness x 3 days.",
                    sort=0,
                    createdAt="2026-06-15T14:30:00Z",
                    updatedAt="2026-06-15T14:35:00Z",
                ),
                DocumentsSection(
                    key="impression",
                    name="Impression",
                    text="Suspected stable angina; EKG ordered.",
                    sort=1,
                    createdAt="2026-06-15T14:30:00Z",
                    updatedAt="2026-06-15T14:35:00Z",
                ),
            ],
            createdAt="2026-06-15T14:30:00Z",
            updatedAt="2026-06-15T14:35:00Z",
            outputLanguage="en-US",
            usageInfo=CommonUsageInfo(creditsConsumed=0.008),
        ),
    ]


# ─── Endpoint ────────────────────────────────────────────────────────


@router.get(
    "/interactions/{interaction_id}/documents/",
    response_model=DocumentsListResponse,
    status_code=200,
)
@router.get(
    "/interactions/{interaction_id}/documents",
    response_model=DocumentsListResponse,
    status_code=200,
)
async def list_v2_tools_interaction_documents(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
) -> DocumentsListResponse:
    """Corti §13.4 Documents Classic — ``GET /interactions/{id}/documents/``.

    Path-scoped to a single interaction UUID. Returns the
    ``{data: DocumentsGetResponse[]}`` envelope. Cycle 5 returns 2
    stub documents per interaction (deterministic, derived from the
    UUID) so SDK callers can verify the path-scoping contract.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return DocumentsListResponse(
        data=_stub_documents_for_interaction(interaction_id),
    )