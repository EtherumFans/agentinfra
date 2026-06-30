"""Corti §13.4 Documents Classic (Planned deprecation) — list shape (Cycle 5).

Cycle 5 (2026-07-01) — LIST endpoint only for the legacy Documents Classic
family. The Corti docs tag this family as "Documents (Classic)" with a
"Planned deprecation" notice; iCoDer mirrors that framing by shipping
the LIST endpoint but explicitly NOT adding a deprecation banner yet
(banners are a Phase 1.5+ frontend concern; the backend wire contract
is the focus of Phase 1.2).

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/documents-classic-list.md`` (7,235
  bytes, fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/documents-classic/list-documents.md``).
  Path: ``GET /interactions/{id}/documents/`` → operationId
  ``documents_list``.

Cycle 5 deliberately closes **only the read path** (list-documents) of
the 5-endpoint Documents Classic family. The other 4 endpoints
(``get-document``, ``generate-document``, ``update-document``,
``delete-document``) land in follow-on cycles once real interaction
storage is wired.

Response envelope (per spec): ``{data: DocumentsGetResponse[]}``.
Each ``DocumentsGetResponse`` carries the document's id, name,
templateRef, isStream flag, sections array, createdAt/updatedAt
timestamps, outputLanguage, and usageInfo.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ─── CommonUsageInfo (shared with cycle 3) ──────────────────────────


class CommonUsageInfo(BaseModel):
    """``CommonUsageInfo`` schema — credits consumed for this request."""
    creditsConsumed: float = Field(..., ge=0.0)


# ─── DocumentsSection (list shape) ──────────────────────────────────


class DocumentsSection(BaseModel):
    """``DocumentsSection`` schema — a single document section row.

    Required: ``key``, ``name``, ``text``, ``sort``, ``createdAt``,
    ``updatedAt``. All fields are server-set; Cycle 5 stub data
    populates everything.
    """
    key: str = Field(..., min_length=1, description="Document section key")
    name: str = Field(..., description="Heading of the section within the document")
    text: str = Field(..., description="Section content text")
    sort: int = Field(..., description="Order of the section within the document")
    createdAt: str = Field(..., description="ISO 8601 timestamp of section creation")
    updatedAt: str = Field(..., description="ISO 8601 timestamp of section update")


# ─── DocumentsGetResponse (single document) ─────────────────────────


class DocumentsGetResponse(BaseModel):
    """``DocumentsGetResponse`` schema — single document representation.

    Required: ``id``, ``name``, ``templateRef``, ``isStream``,
    ``sections``, ``createdAt``, ``updatedAt``, ``outputLanguage``,
    ``usageInfo``.
    """
    id: str = Field(..., description="UUID of the generated document")
    name: str = Field(..., description="Name of the generated document")
    templateRef: str = Field(..., description="Reference for the used template")
    isStream: bool = Field(..., description="True if generated via Streams WSS")
    sections: List[DocumentsSection] = Field(default_factory=list)
    createdAt: str = Field(..., description="ISO 8601 timestamp of document creation")
    updatedAt: str = Field(..., description="ISO 8601 timestamp of last update")
    outputLanguage: str = Field(..., description="BCP 47 language tag of the generated output")
    usageInfo: CommonUsageInfo


# ─── DocumentsListResponse (envelope) ──────────────────────────────


class DocumentsListResponse(BaseModel):
    """``DocumentsListResponse`` schema — list-documents response envelope.

    Required: ``data`` (array of DocumentsGetResponse). Other top-level
    fields (pagination cursors etc.) are intentionally NOT modeled here
    because the captured spec declares only ``data`` as required.
    """
    data: List[DocumentsGetResponse]