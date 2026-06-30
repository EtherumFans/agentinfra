"""Corti §13.4 Guided Documents — wire-shape parity (Cycle 3).

Cycle 3 (2026-06-30) — first GA-shaped surface from the §13.4 TextGen
family beyond Streams / FactsR. Spec source:
``docs/corti-reverse-engineered/guided-documents-generate.md`` (fetched
from ``https://docs.corti.ai/api-reference/guided-documents/generate-a-structured-document.md``).

This module covers **only the simplest path** that can be closed in one
cycle: the ``templateRef`` supply path + ``X-Corti-Retention-Policy: none``
header (ephemeral response). The other two paths (assemblyTemplate,
dynamicTemplate) are documented in the OpenAPI spec but are out of scope
for Cycle 3; their schemas would be added in a follow-on cycle.

Field names verbatim from the spec (CamelCase). Required/optional reflects
the OpenAPI ``required`` arrays.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ─── Shared sub-schemas ──────────────────────────────────────────────


class GuidedLabel(BaseModel):
    """``GuidedLabel`` schema — key/value tag for documents/templates."""
    key: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class CommonUsageInfo(BaseModel):
    """``CommonUsageInfo`` schema — billing metadata returned on every doc gen."""
    creditsConsumed: float = Field(..., ge=0.0, description="Credits billed for this request")


class CommonTextContext(BaseModel):
    """``CommonTextContext`` schema — plain text input context."""
    type: Literal["text"] = Field(..., description='Discriminator; always "text"')
    text: str = Field(..., min_length=1, description="Free-form clinical text")


# ─── Request shape ──────────────────────────────────────────────────


class GuidedDocumentsGenerateBase(BaseModel):
    """``GuidedDocumentsGenerateBase`` — fields shared by all 3 request variants.

    Per the spec: ``outputLanguage`` is always required; **at least one** of
    ``context`` or ``interactionId`` must be supplied.
    """
    outputLanguage: str = Field(..., description="BCP 47 language tag for the generated output")
    context: Optional[List[CommonTextContext]] = Field(
        default=None,
        description="Ordered list of context items (text/transcript/facts). At least one of context or interactionId must be supplied.",
    )
    interactionId: Optional[str] = Field(
        default=None, description="UUID of an interaction whose facts/transcripts auto-fill context"
    )
    labels: Optional[List[GuidedLabel]] = Field(
        default=None, description="Key/value labels for filtering in LIST /documents"
    )


class GuidedTemplateRef(BaseModel):
    """``GuidedTemplateRef`` schema — references a stored template.

    Cycle 3 supports the plain ``templateRef`` (no overrides) path only;
    ``overrides`` is left as future work because its auto-save-as-aggregate
    semantics don't fit a single-cycle回环 gate.
    """
    templateId: str = Field(..., description="UUID of a stored template")
    templateVersionId: Optional[str] = Field(
        default=None, description="Optional explicit template version; defaults to published version"
    )


class GuidedDocumentsGenerateByTemplateRef(BaseModel):
    """``GuidedDocumentsGenerateByTemplateRef`` schema — the simplest request variant."""
    outputLanguage: str = Field(..., description="BCP 47 language tag")
    context: Optional[List[CommonTextContext]] = Field(default=None)
    interactionId: Optional[str] = Field(default=None)
    labels: Optional[List[GuidedLabel]] = Field(default=None)
    templateRef: GuidedTemplateRef


class GuidedDocumentsGenerateRequest(BaseModel):
    """``GuidedDocumentsGenerateRequest`` schema — the oneOf envelope.

    Discriminator: ``templateRef`` is present (Cycle 3). ``assemblyTemplate``
    and ``dynamicTemplate`` are accepted by the OpenAPI spec but explicitly
    rejected by iCoDer Cycle 3 with a 422 — they'll land in a later cycle.
    """
    templateRef: Optional[GuidedTemplateRef] = Field(default=None)


# ─── Response shape (ephemeral only, Cycle 3) ───────────────────────


class GuidedEphemeralDocument(BaseModel):
    """``GuidedEphemeralDocument`` schema — generated-but-not-saved document."""
    name: str = Field(..., min_length=1)
    templateId: str = Field(..., description="UUID of the template used for generation")
    templateVersionId: str = Field(..., description="UUID of the specific template version")
    language: str = Field(..., description="BCP 47 language tag of the generated output")
    interactionId: Optional[str] = Field(default=None)
    stringDocument: dict = Field(
        ..., description="Section key → rendered string output (free-form map)"
    )
    structuredDocument: Optional[dict] = Field(
        default=None, description="Section key → structured object output (free-form map)"
    )
    labels: List[GuidedLabel] = Field(default_factory=list)


class GuidedDocumentsCreateEphemeralResponse(BaseModel):
    """``GuidedDocumentsCreateEphemeralResponse`` schema — 200 response when
    ``X-Corti-Retention-Policy: none`` header is sent (document generated but
    not persisted).
    """
    document: GuidedEphemeralDocument
    usageInfo: CommonUsageInfo


# ─── Error envelope ─────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """``ErrorResponse`` schema — Corti-standard error envelope.

    Required: ``requestid``, ``status``, ``type``, ``detail``.
    Optional: ``validationErrors[]``.
    """
    requestid: str = Field(..., description="Server-assigned request correlation id")
    status: int = Field(..., ge=100, le=599, description="HTTP status code")
    type: str = Field(..., description="Error type identifier (e.g. 'invalid_request')")
    detail: str = Field(..., description="Human-readable error detail")
    validationErrors: Optional[List[dict]] = Field(
        default=None, description="Optional per-field validation errors (map[str, str])"
    )