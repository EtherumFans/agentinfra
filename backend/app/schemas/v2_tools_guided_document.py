"""Corti §13.4 Guided Documents — wire-shape parity (Cycle 3).

Initial GA-shaped surface from the §13.4 TextGen
family beyond Streams / FactsR. Spec source:
``docs/corti-reverse-engineered/guided-documents-generate.md`` (fetched
from ``https://docs.corti.ai/api-reference/guided-documents/generate-a-structured-document.md``).

This module covers reference, assembly, and dynamic template supply paths;
ephemeral and saved-retention responses; persisted Facts/STT context; runtime
overrides; and recursive structured-output schemas.

Field names verbatim from the spec (CamelCase). Required/optional reflects
the OpenAPI ``required`` arrays.
"""

from __future__ import annotations

import json
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


MAX_GUIDED_REQUEST_BYTES = 1024 * 1024
MAX_GUIDED_CONTEXT_CHARS = 200_000


# ─── Shared sub-schemas ──────────────────────────────────────────────


class GuidedLabel(BaseModel):
    """``GuidedLabel`` schema — key/value tag for documents/templates."""
    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=512)


class CommonUsageInfo(BaseModel):
    """``CommonUsageInfo`` schema — billing metadata returned on every doc gen."""
    creditsConsumed: float = Field(..., ge=0.0, description="Credits billed for this request")


class CommonTextContext(BaseModel):
    """``CommonTextContext`` schema — plain text input context."""
    type: Literal["text"] = Field(..., description='Discriminator; always "text"')
    text: str = Field(..., min_length=1, max_length=200_000, description="Free-form clinical text")


class GuidedDocumentTranscriptSegmentMinimal(BaseModel):
    text: str = Field(..., min_length=1, max_length=4_000)
    channel: Optional[int] = Field(default=None, ge=0)
    participant: Optional[int] = Field(default=None, ge=0)
    speakerId: Optional[int] = Field(default=None, ge=0)
    start: Optional[int] = Field(default=None, ge=0)
    end: Optional[int] = Field(default=None, ge=0)


class GuidedDocumentTranscriptMinimal(BaseModel):
    transcripts: List[GuidedDocumentTranscriptSegmentMinimal] = Field(..., min_length=1, max_length=2_000)
    metadata: Optional[dict[str, Any]] = None


class CommonTranscriptContext(BaseModel):
    type: Literal["transcript"]
    transcript: GuidedDocumentTranscriptMinimal


class GuidedDocumentFactMinimal(BaseModel):
    text: str = Field(..., min_length=1, max_length=4_000)
    group: Optional[str] = Field(default=None, max_length=128)


class CommonFactsContext(BaseModel):
    type: Literal["facts"]
    facts: List[GuidedDocumentFactMinimal] = Field(..., min_length=1, max_length=2_000)


GuidedDocumentContext = CommonTextContext | CommonTranscriptContext | CommonFactsContext


# ─── Request shape ──────────────────────────────────────────────────


class GuidedDocumentsGenerateBase(BaseModel):
    """``GuidedDocumentsGenerateBase`` — fields shared by all 3 request variants.

    Per the spec: ``outputLanguage`` is always required; **at least one** of
    ``context`` or ``interactionId`` must be supplied.
    """
    outputLanguage: str = Field(..., min_length=1, max_length=35, description="BCP 47 language tag for the generated output")
    context: Optional[List[GuidedDocumentContext]] = Field(
        default=None,
        max_length=64,
        description="Ordered list of context items (text/transcript/facts). At least one of context or interactionId must be supplied.",
    )
    interactionId: Optional[str] = Field(
        default=None, max_length=160, description="UUID of an interaction whose facts/transcripts auto-fill context"
    )
    labels: Optional[List[GuidedLabel]] = Field(
        default=None, max_length=100, description="Key/value labels for filtering in LIST /documents"
    )


class GuidedTemplateRef(BaseModel):
    """``GuidedTemplateRef`` schema — references a stored template.

    The endpoint supports the plain ``templateRef`` (no overrides) path;
    ``overrides`` is left as future work because its auto-save-as-aggregate
    semantics don't fit a single-cycle回环 gate.
    """
    templateId: str = Field(..., min_length=1, max_length=160, description="UUID of a stored template")
    templateVersionId: Optional[str] = Field(
        default=None, max_length=160, description="Optional explicit template version; defaults to published version"
    )
    overrides: Optional[dict[str, Any]] = None


class GuidedTemplateInstructions(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20_000)


class GuidedSectionInstructions(BaseModel):
    contentPrompt: str = Field(..., min_length=1, max_length=20_000)
    writingStylePrompt: Optional[str] = Field(default=None, max_length=20_000)
    miscPrompt: Optional[str] = Field(default=None, max_length=20_000)


class GuidedSectionGeneration(BaseModel):
    heading: str = Field(..., min_length=1, max_length=256)
    instructions: GuidedSectionInstructions
    outputSchema: dict[str, Any]


class GuidedDynamicInline(BaseModel):
    instructions: GuidedTemplateInstructions
    sections: List[GuidedSectionGeneration] = Field(..., min_length=1, max_length=100)


class GuidedDynamicRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    generation: GuidedDynamicInline


class GuidedAssemblySectionRef(BaseModel):
    sectionId: str = Field(..., min_length=1, max_length=160)
    sectionVersionId: Optional[str] = Field(default=None, max_length=160)
    overrides: Optional[dict[str, Any]] = None


class GuidedAssemblyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    instructions: Optional[GuidedTemplateInstructions] = None
    sectionRefs: List[GuidedAssemblySectionRef] = Field(..., min_length=1, max_length=100)


class GuidedDocumentsGenerateByTemplateRef(BaseModel):
    """``GuidedDocumentsGenerateByTemplateRef`` schema — the simplest request variant."""
    outputLanguage: str = Field(..., min_length=1, max_length=35, description="BCP 47 language tag")
    context: Optional[List[GuidedDocumentContext]] = Field(default=None, max_length=64)
    interactionId: Optional[str] = Field(default=None, max_length=160)
    labels: Optional[List[GuidedLabel]] = Field(default=None, max_length=100)
    templateRef: GuidedTemplateRef


class GuidedDocumentsGenerateRequest(BaseModel):
    """Corti oneOf request envelope for all three template supply paths."""
    outputLanguage: str = Field(..., min_length=1, max_length=35)
    context: Optional[List[GuidedDocumentContext]] = Field(default=None, max_length=64)
    interactionId: Optional[str] = Field(default=None, max_length=160)
    labels: Optional[List[GuidedLabel]] = Field(default=None, max_length=100)
    templateRef: Optional[GuidedTemplateRef] = Field(default=None)
    assemblyTemplate: Optional[GuidedAssemblyRequest] = None
    dynamicTemplate: Optional[GuidedDynamicRequest] = None

    @model_validator(mode="after")
    def _exactly_one_template_supply(self):
        supplied = sum(value is not None for value in (
            self.templateRef, self.assemblyTemplate, self.dynamicTemplate
        ))
        if supplied != 1:
            raise ValueError(
                "exactly one of templateRef, assemblyTemplate, or dynamicTemplate is required"
            )
        context_chars = 0
        for item in self.context or []:
            if isinstance(item, CommonTextContext):
                context_chars += len(item.text)
            elif isinstance(item, CommonFactsContext):
                context_chars += sum(len(fact.text) for fact in item.facts)
            elif isinstance(item, CommonTranscriptContext):
                context_chars += sum(
                    len(segment.text) for segment in item.transcript.transcripts
                )
        if context_chars > MAX_GUIDED_CONTEXT_CHARS:
            raise ValueError(
                f"context text exceeds {MAX_GUIDED_CONTEXT_CHARS} characters"
            )
        request_bytes = len(
            json.dumps(
                self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        )
        if request_bytes > MAX_GUIDED_REQUEST_BYTES:
            raise ValueError(
                f"request exceeds {MAX_GUIDED_REQUEST_BYTES} bytes"
            )
        return self


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


class GuidedDocument(GuidedEphemeralDocument):
    """Generated document stored in the authenticated tenant boundary."""
    id: str = Field(..., description="Server-assigned document UUID")
    createdAt: str = Field(..., description="ISO 8601 creation timestamp")
    updatedAt: str = Field(..., description="ISO 8601 update timestamp")


class GuidedDocumentsCreateResponse(BaseModel):
    """201 response for the default saved-retention behavior."""
    document: GuidedDocument
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
