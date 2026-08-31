"""Corti Documents Classic (planned deprecation) wire schemas.

These models cover the persisted document list/get representation and the
update payload used by the legacy compatibility lifecycle.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/documents-classic-list.md`` (7,235
  bytes, fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/documents-classic/list-documents.md``).
  Path: ``GET /interactions/{id}/documents/`` → operationId
  ``documents_list``.

Response envelope (per spec): ``{data: DocumentsGetResponse[]}``.
Each ``DocumentsGetResponse`` carries the document's id, name,
templateRef, isStream flag, sections array, createdAt/updatedAt
timestamps, outputLanguage, and usageInfo.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─── CommonUsageInfo (shared with cycle 3) ──────────────────────────


class CommonUsageInfo(BaseModel):
    """``CommonUsageInfo`` schema — credits consumed for this request."""
    creditsConsumed: float = Field(..., ge=0.0)


class DocumentsFactContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=65536)
    group: Optional[str] = Field(default=None, max_length=128)
    source: Optional[Literal["core", "system", "user"]] = None

    @field_validator("text")
    @classmethod
    def _fact_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("fact text must not be blank")
        return value


class DocumentsTranscriptContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Optional[int] = None
    participant: Optional[int] = None
    speakerId: Optional[int] = None
    text: str = Field(..., min_length=1, max_length=262144)
    start: Optional[int] = Field(default=None, ge=0)
    end: Optional[int] = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def _transcript_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("transcript text must not be blank")
        return value


class DocumentsContextWithFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["facts"]
    data: List[DocumentsFactContext] = Field(..., min_length=1)


class DocumentsContextWithTranscript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["transcript"]
    data: DocumentsTranscriptContextData


class DocumentsContextWithString(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["string"]
    data: str = Field(..., min_length=1, max_length=262144)

    @field_validator("data")
    @classmethod
    def _string_data_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("string context must not be blank")
        return value


DocumentsContext = Annotated[
    Union[
        DocumentsContextWithFacts,
        DocumentsContextWithTranscript,
        DocumentsContextWithString,
    ],
    Field(discriminator="type"),
]


class DocumentsSectionOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=128)
    nameOverride: Optional[str] = Field(default=None, min_length=1, max_length=256)
    writingStyleOverride: Optional[str] = Field(default=None, max_length=8192)
    formatRuleOverride: Optional[str] = Field(default=None, max_length=8192)
    additionalInstructionsOverride: Optional[str] = Field(default=None, max_length=8192)
    contentOverride: Optional[str] = Field(default=None, max_length=8192)


class DocumentsTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: Optional[List[DocumentsSectionOverride]] = Field(default=None, min_length=1)
    sectionKeys: Optional[List[str]] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, max_length=4096)
    documentName: Optional[str] = Field(default=None, max_length=256)
    additionalInstructions: Optional[str] = Field(default=None, max_length=8192)
    additionalInstructionsOverride: Optional[str] = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def _exactly_one_section_supply(self) -> "DocumentsTemplate":
        if (self.sections is None) == (self.sectionKeys is None):
            raise ValueError("exactly one of sections or sectionKeys is required")
        if self.sectionKeys is not None:
            cleaned = [item.strip() for item in self.sectionKeys]
            if any(not item for item in cleaned) or len(cleaned) != len(set(cleaned)):
                raise ValueError("sectionKeys must be unique non-blank strings")
            self.sectionKeys = cleaned
        if self.sections is not None:
            keys = [item.key.strip() for item in self.sections]
            if any(not item for item in keys) or len(keys) != len(set(keys)):
                raise ValueError("section override keys must be unique non-blank strings")
            for item, key in zip(self.sections, keys):
                item.key = key
        return self


class DocumentsCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: List[DocumentsContext] = Field(..., min_length=1)
    templateKey: Optional[str] = Field(default=None, min_length=1, max_length=256)
    template: Optional[DocumentsTemplate] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    outputLanguage: str = Field(..., min_length=1, max_length=32)
    disableGuardrails: bool = False
    documentationMode: Optional[Literal["global_sequential", "routed_parallel"]] = None

    @model_validator(mode="after")
    def _validate_request(self) -> "DocumentsCreateRequest":
        if (self.templateKey is None) == (self.template is None):
            raise ValueError("exactly one of templateKey or template is required")
        if len(self.context) > 1 and any(item.type != "transcript" for item in self.context):
            raise ValueError("multiple context objects are supported only for transcript")
        if self.templateKey is not None:
            self.templateKey = self.templateKey.strip()
            if not self.templateKey:
                raise ValueError("templateKey must not be blank")
        self.outputLanguage = self.outputLanguage.strip()
        if not self.outputLanguage:
            raise ValueError("outputLanguage must not be blank")
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("name must not be blank")
        return self


# ─── DocumentsSection (list shape) ──────────────────────────────────


class DocumentsSection(BaseModel):
    """``DocumentsSection`` schema — a single document section row.

    Required: ``key``, ``name``, ``text``, ``sort``, ``createdAt``,
    ``updatedAt``. The persistence layer supplies server timestamps.
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


class DocumentsUpdateSection(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    text: str = Field(..., max_length=65536)
    sort: int = Field(..., ge=0)


class DocumentsUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    sections: Optional[List[DocumentsUpdateSection]] = None


# ─── DocumentsListResponse (envelope) ──────────────────────────────


class DocumentsListResponse(BaseModel):
    """``DocumentsListResponse`` schema — list-documents response envelope.

    Required: ``data`` (array of DocumentsGetResponse). Other top-level
    fields (pagination cursors etc.) are intentionally NOT modeled here
    because the captured spec declares only ``data`` as required.
    """
    data: List[DocumentsGetResponse]
