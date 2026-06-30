"""Corti §3.1 Medical Coding request/response schemas.

Phase 1.1 (2026-06-30) — align iCoDer Medical Coding HTTP API with the
documented Corti contract at ``api.eu.corti.app/v2/tools/coding/``.

Shape:

Request:
    {
      "context": [{"text": "...", "type": "text"}, ...],
      "system":  ["icd10cn-outpatient", ...]      # iCoDer-only system names
    }

Response:
    {
      "codes": [
        {
          "system": "icd10cn-outpatient",
          "code":   "I50.900",
          "display": "心力衰竭 ...",
          "evidences": [
            {"contextIndex": 0, "text": "...", "start": 110, "end": 128}
          ],
          "alternatives": [
            {"code": "I50.907", "display": "..."}
          ]
        }
      ]
    }

Field maps (Corti ↔ iCoDer Runtime) are documented in
``docs/PHASE_1_1_MEDICAL_CODING_PATH_SCHEMA.md``.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ─── Request ──────────────────────────────────────────────────────────


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


class CodingRequest(BaseModel):
    """Corti §3.1 ``POST /v2/tools/coding`` request body."""
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
