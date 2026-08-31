"""iCoDer Medical Coding v2 schemas — Phase 1.1 + Cycle 18.

Phase 1.1 (2026-06-30) — iCoDer 5-stage MedCodER pipeline at
``POST /api/v2/tools/coding/icoder/`` (Chinese-only ICD-10-CN / ICD-9-CM-3).

Cycle 18 (2026-07-01) — Corti §13.6 ``codes_predict`` at
``POST /api/v2/tools/coding/`` (15 coding systems, stateless single-shot
prediction per Corti OpenAPI spec).

The two endpoints share the *evidence* / *alternative* inner shapes
(``CodingEvidence``, ``CodingAlternative``) but differ on:

  - Request envelope: cycle 18 adds ``filter.include/exclude/expand``.
  - Response envelope: cycle 18 splits into ``codes[]`` (predicted) +
    ``candidates[]`` (lower-confidence) + ``usageInfo.creditsConsumed``.
  - Coding system vocabulary: cycle 18 accepts all 15 Corti
    ``CommonCodingSystemEnum`` values (no Chinese-only restriction).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Common shapes (shared between Phase 1.1 + Cycle 18) ────────────


class CodingContextItem(BaseModel):
    """One block of source text the model should consider.

    Mirrors Corti's context[] element. ``type`` is a free-form discriminator
    (Corti docs currently only produce ``text``); iCoDer keeps the field so
    future audio / image contexts can be added without breaking the wire
    format.
    """
    text: str = Field(default="", description="Source text for this context block")
    type: str = Field(default="text", description="Modality discriminator: text | audio | image (only text is wired today)")

    @field_validator("text")
    @classmethod
    def _text_must_be_string(cls, v: str) -> str:
        # Allow empty string; the route handler rejects fully-empty input.
        return v if v is not None else ""


# ─── Phase 1.1 — iCoDer MedCodER pipeline request ────────────────────


class CodingRequest(BaseModel):
    """Phase 1.1 ``POST /api/v2/tools/coding/icoder/`` request body.

    Chinese-only system names. Corti US-style names are rejected with 400.
    """
    context: List[CodingContextItem] = Field(
        default_factory=list,
        description="One or more context blocks (text spans, future: audio/image)",
    )
    system: List[str] = Field(
        default_factory=list,
        description=(
            "iCoDer coding system namespace. Only iCoDer Chinese-system names are "
            "accepted: icd10cn-outpatient / icd10cn-inpatient / "
            "icd9cm3-procedure / icd9cm3-diagnostic. Corti US-style names "
            "(icd10cm-*, icd10pcs, icd9cm, cpt) intentionally return 400."
        ),
    )


# ─── Response ─────────────────────────────────────────────────────────


class CodingEvidence(BaseModel):
    """One char-offset citation inside ``context[contextIndex].text``.

    Mirrors Corti's ``evidences[]`` element. ``start`` / ``end`` are
    inclusive-exclusive offsets into the *concatenated* context block
    (i.e. ``context[contextIndex].text[start:end] == text``).
    """
    contextIndex: int = Field(
        default=0,
        ge=0,
        description="0-based index into the request's context[] list",
    )
    text: str = Field(default="", description="The citation text itself")
    start: int = Field(default=0, ge=0, description="char_start (inclusive)")
    end: int = Field(default=0, ge=0, description="char_end (exclusive)")


class CodingAlternative(BaseModel):
    """One reranked alternative for a code (top-K[1:5] of the same disease)."""
    code: str = Field(default="", description="iCoDer-system code (e.g. I50.907)")
    display: str = Field(default="", description="Long Chinese display name from the code dictionary")


class CodingCode(BaseModel):
    """One final coding result for a single disease/procedure mention.

    Mirrors Corti's ``codes[]`` element. ``system`` echoes whatever the caller
    passed in (iCoDer Chinese system), so a SDK caller can correlate the
    output back to their request without consulting docs.corti.ai again.
    """
    system: str = Field(default="icd10cn-outpatient", description="Echo of request's system[0]")
    code: str = Field(default="", description="Final primary code from rerank (final_top_k[0])")
    display: str = Field(default="", description="Long display name looked up from the iCoDer code dictionary")
    evidences: List[CodingEvidence] = Field(
        default_factory=list,
        description="Char-offset citations linking this code to source context",
    )
    alternatives: List[CodingAlternative] = Field(
        default_factory=list,
        description="Rerank alternatives (final_top_k[1:5])",
    )


class CodingResponse(BaseModel):
    """Corti §3.1 ``POST /v2/tools/coding`` response body."""
    codes: List[CodingCode] = Field(
        default_factory=list,
        description="One entry per disease/procedure mention extracted from the source text",
    )


# ─── Constants ────────────────────────────────────────────────────────


# Accepted iCoDer system namespace. Corti US-style names are explicitly
# rejected — see the route handler for the 400 path.
#
# This set is *both* the allow-list (request) and the documented public
# vocabulary (response echo). Phase 1.2 will register ``coding`` as an OAuth
# capability scope; this constant is the SSOT for what system values map
# to it.
ICODER_CODING_SYSTEMS: frozenset[str] = frozenset({
    "icd10cn-outpatient",   # ICD-10-CN 门诊
    "icd10cn-inpatient",    # ICD-10-CN 住院
    "icd9cm3-procedure",    # ICD-9-CM-3 手术与操作
    "icd9cm3-diagnostic",   # ICD-9-CM-3 诊断性操作
})


def default_coding_system() -> str:
    """Default system when caller supplies an empty system[] (Phase 1.1 fallback)."""
    return "icd10cn-outpatient"


# ─── Cycle 18 — Corti §13.6 codes_predict ────────────────────────────
# Aligned with ``docs/corti-reverse-engineered/codes-predict-codes.md``.


# 15-system enum from the Corti OpenAPI CommonCodingSystemEnum:
#   - icd10cm-inpatient / icd10cm-outpatient (US)
#   - icd10pcs (US procedure)
#   - cpt (US procedure)
#   - icd10int-inpatient / icd10int-outpatient (international)
#   - icd10uk-inpatient / icd10uk-outpatient (UK)
#   - cim10fr-inpatient / cim10fr-outpatient (France)
#   - icd10gm-inpatient / icd10gm-outpatient (Germany)
#   - opcs4 (UK procedure)
#   - ops (Germany procedure)
#   - ccam (France procedure)
# The canonical Corti-compatible endpoint accepts these 15 values verbatim;
# its runtime projection still requires exact source evidence and a real,
# non-degraded provider response.
CORTI_COMMON_CODING_SYSTEMS: frozenset[str] = frozenset({
    "icd10cm-inpatient",
    "icd10cm-outpatient",
    "icd10pcs",
    "cpt",
    "icd10int-inpatient",
    "icd10int-outpatient",
    "icd10uk-inpatient",
    "icd10uk-outpatient",
    "cim10fr-inpatient",
    "cim10fr-outpatient",
    "icd10gm-inpatient",
    "icd10gm-outpatient",
    "opcs4",
    "ops",
    "ccam",
})


class CommonTextContext(BaseModel):
    """One text-based context block (mirrors Corti ``CommonTextContext``)."""
    type: str = Field(default="text", description="Always ``text`` for text-based context")
    text: str = Field(default="", description="Source text for this context block", min_length=0)

    @field_validator("type")
    @classmethod
    def _type_must_be_text(cls, v: str) -> str:
        if v != "text":
            raise ValueError(f"CommonTextContext.type must be 'text', got {v!r}")
        return v


class CommonDocumentIDContext(BaseModel):
    """One documentId-based context block (mirrors Corti ``CommonDocumentIDContext``)."""
    type: str = Field(default="documentId", description="Always ``documentId`` for document-based context")
    documentId: str = Field(default="", description="A referenced document ID")

    @field_validator("type")
    @classmethod
    def _type_must_be_documentid(cls, v: str) -> str:
        if v != "documentId":
            raise ValueError(f"CommonDocumentIDContext.type must be 'documentId', got {v!r}")
        return v


class CommonAIContext(BaseModel):
    """Discriminated union: text OR documentId (mirrors Corti ``CommonAIContext``).

    The selected variant must contain exactly its own non-empty value. This
    prevents an ambiguous request from silently preferring one source over
    another before evidence offsets are calculated.
    """
    type: str = Field(default="text", description="Either ``text`` or ``documentId``")
    text: Optional[str] = Field(default=None, description="Source text (when type=text)")
    documentId: Optional[str] = Field(default=None, description="Referenced document ID (when type=documentId)")

    @model_validator(mode="after")
    def _validate_variant(self) -> "CommonAIContext":
        if self.type == "text":
            if not (self.text or "").strip():
                raise ValueError("text context requires a non-empty text value")
            if self.documentId is not None:
                raise ValueError("text context must not include documentId")
            return self
        if self.type == "documentId":
            if not (self.documentId or "").strip():
                raise ValueError("documentId context requires a non-empty documentId value")
            if self.text is not None:
                raise ValueError("documentId context must not include text")
            return self
        raise ValueError("context type must be either 'text' or 'documentId'")


class CodesFilter(BaseModel):
    """Optional filter to restrict the set of codes the model can predict."""
    include: List[str] = Field(
        default_factory=list,
        max_length=100,
        description="Codes or categories to include. When empty, the full set of codes for the requested systems is used.",
    )
    exclude: List[str] = Field(
        default_factory=list,
        max_length=100,
        description="Codes or categories to subtract from the include set.",
    )
    expand: Optional[bool] = Field(
        default=True,
        description="When true (default), category codes are expanded to their leaf codes.",
    )

    @field_validator("include", "exclude")
    @classmethod
    def _validate_filter_terms(cls, values: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for raw in values:
            value = (raw or "").strip()
            if not value:
                raise ValueError("code filter entries must not be empty")
            if len(value) > 64:
                raise ValueError("code filter entries must be at most 64 characters")
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError("code filter entries must not contain control characters")
            key = value.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(value)
        return normalized

    @model_validator(mode="after")
    def _combined_filter_size_is_bounded(self) -> "CodesFilter":
        if len(self.include) + len(self.exclude) > 100:
            raise ValueError("include and exclude may contain at most 100 entries combined")
        return self


class CodesGeneralPredictRequest(BaseModel):
    """Cycle 18 — Corti §13.6 ``POST /tools/coding/`` request body.

    Distinct from Phase 1.1's ``CodingRequest``: accepts the 15-system
    Corti vocabulary, supports ``documentId`` context, and adds optional
    ``filter.include/exclude/expand``.
    """
    system: List[str] = Field(
        default_factory=list,
        description=(
            "List of Corti coding systems. Must be a non-empty list of "
            "CommonCodingSystemEnum values (max 15). Mirrors the spec's "
            "``system: array<CommonCodingSystemEnum>`` with minItems=1, "
            "maxItems=15, uniqueItems=true."
        ),
    )
    context: List[CommonAIContext] = Field(
        default_factory=list,
        description=(
            "List of text or documentId context blocks. Evidence indices in "
            "the response map to this array."
        ),
    )
    filter: Optional[CodesFilter] = Field(
        default=None,
        description="Optional filter to restrict predicted codes.",
    )


class CommonUsageInfo(BaseModel):
    """Credits consumed for this request (mirrors Corti ``CommonUsageInfo``)."""
    creditsConsumed: float = Field(
        default=0.0,
        description="Number of credits consumed by this request.",
        ge=0.0,
    )


class CodesGeneralReadResponse(BaseModel):
    """One predicted or candidate code record (mirrors Corti ``CodesGeneralReadResponse``)."""
    system: str = Field(default="", description="The Corti coding system used")
    code: str = Field(default="", description="The medical code")
    display: str = Field(default="", description="Description of the medical code")
    evidences: List[CodingEvidence] = Field(
        default_factory=list,
        description="The evidence for the prediction (char-span citations)",
    )
    alternatives: List[CodingAlternative] = Field(
        default_factory=list,
        description="Codes the model also considered for this prediction.",
    )


class CodesGeneralResponse(BaseModel):
    """Cycle 18 — Corti §13.6 ``POST /tools/coding/`` response body.

    Distinct from Phase 1.1's ``CodingResponse``:
      - adds ``candidates[]`` (lower-confidence codes the model considered
        but excluded from the predicted set)
      - adds ``usageInfo.creditsConsumed``
    """
    codes: List[CodesGeneralReadResponse] = Field(
        default_factory=list,
        description="Codes predicted by the model.",
    )
    candidates: List[CodesGeneralReadResponse] = Field(
        default_factory=list,
        description="Lower-confidence codes the model considered but excluded from the predicted set.",
    )
    usageInfo: CommonUsageInfo = Field(
        default_factory=CommonUsageInfo,
        description="Credits consumed for this request.",
    )


def default_corti_coding_system() -> str:
    """Default system when caller supplies an empty system[] (Cycle 18 fallback)."""
    return "icd10cm-outpatient"
