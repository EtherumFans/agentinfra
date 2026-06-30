"""Corti §3.2 / §13.4 FactsR™ request/response schemas.

Phase 1.2 cycle 1 (2026-06-30) — align iCoDer's text-generation surface to the
documented Corti contract at ``api.eu.corti.app/v2/tools/extract-facts``.

This is the first GA endpoint of the §13.4 Text Generation five-Endpoint
family (``Streams`` WSS + ``FactsR`` REST). Captured by interception in
``docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json``.

Shape:

Request:
    {
      "context": [{"text": "...", "type": "text"}, ...],
      "outputLanguage": "en-US"
    }

Response:
    {
      "facts": [
        {"group": "chief-complaint", "text": "...", "value": "..."},
        {"group": "history-of-present-illness", "text": "...", "value": "..."},
        ...
      ],
      "outputLanguage": "en-US",
      "usageInfo": {"creditsConsumed": 0.011}
    }

Field semantics (Corti docs):
- ``facts[]`` — extracted clinical facts, ordered roughly by importance.
- ``facts[].group`` — clinical category key (kebab-case from
  ``/v2/factgroups/``); see :data:`CORTI_FACT_GROUPS` for the canonical set.
- ``facts[].text`` — the natural-language phrasing of the fact.
- ``facts[].value`` — for vital-signs / lab / demographic style groups, this
  is the structured value (often equal to ``text``).
- ``outputLanguage`` — echo of the request. ``en-US`` is the only output
  language Corti currently supports (per release notes 2026-05).
- ``usageInfo.creditsConsumed`` — credits billed for the inference call.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ─── Request ──────────────────────────────────────────────────────────


class FactsContextItem(BaseModel):
    """One block of source text the model should consider for fact extraction.

    Mirrors ``context[]`` in ``/api/icoder/coding-review-v2`` (Phase 1.1)
    and the canonical Corti shape. ``type`` is a free-form discriminator
    (today only ``text`` is wired); iCoDer keeps the field so future audio
    transcriptions can be fed without breaking the wire format.
    """
    text: str = Field(default="", description="Source text to extract facts from")
    type: str = Field(default="text", description="Modality discriminator: text (today); audio reserved for Phase 1.3")


class FactsExtractRequest(BaseModel):
    """Corti §3.2 ``POST /v2/tools/extract-facts`` request body."""
    context: List[FactsContextItem] = Field(
        default_factory=list,
        description="One or more context blocks (text spans). At least one must contain non-whitespace text.",
    )
    outputLanguage: str = Field(
        default="en-US",
        description=(
            "Output language code. Corti docs (2026-05 release) only "
            "support ``en-US``; iCoDer also accepts ``zh-CN`` natively "
            "and falls back to ``en-US`` for other codes with a warning."
        ),
    )

    @field_validator("outputLanguage")
    @classmethod
    def _normalise_language(cls, v: str) -> str:
        # Allow caller to send "en", "en-us", "EN-US"; store canonical form.
        v = (v or "").strip()
        if not v:
            return "en-US"
        return v


# ─── Response ─────────────────────────────────────────────────────────


class FactItem(BaseModel):
    """One extracted clinical fact (Corti ``facts[]`` element).

    The ``group`` key is the *kebab-case* identifier from Corti's
    ``/v2/factgroups/`` taxonomy; iCoDer forwards whatever the LLM returns
    without forcing it into the canonical set so that domain-specific or
    future additions don't get silently dropped.
    """
    group: str = Field(
        default="",
        description="kebab-case clinical category key (e.g. 'chief-complaint', 'vital-signs')",
    )
    text: str = Field(default="", description="Natural-language description of the fact")
    value: str = Field(default="", description="Structured value (often equal to ``text``)")


class FactUsageInfo(BaseModel):
    """Mirrors Corti ``usageInfo`` block."""
    creditsConsumed: float = Field(default=0.0, ge=0.0, description="Credits billed for this inference")


class FactExtractResponse(BaseModel):
    """Corti §3.2 ``POST /v2/tools/extract-facts`` response body."""
    facts: List[FactItem] = Field(
        default_factory=list,
        description="One item per extracted clinical fact",
    )
    outputLanguage: str = Field(default="en-US", description="Echo of request.outputLanguage")
    usageInfo: FactUsageInfo = Field(
        default_factory=FactUsageInfo,
        description="Billing + token usage metadata",
    )


# ─── Constants ────────────────────────────────────────────────────────


# Canonical Corti fact-group vocabulary (taken from the
# ``/v2/factgroups/`` capture in
# ``docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json``
# — 28+ groups at last count). The route only validates well-formedness,
# not membership, so callers can experiment with new keys without hitting 400.
CORTI_FACT_GROUPS: frozenset[str] = frozenset({
    "demographics",
    "chief-complaint",
    "history-of-present-illness",
    "past-medical-history",
    "medications-prior-to-visit",
    "family-history",
    "allergies",
    "social-history",
    "vital-signs",
    "abnormal-physical-findings",
    "imaging-results",
    "lab-results",
    "assessment",
    "actions",
    "instructions",
    "plan",
    "follow-up",
})

# Languages that iCoDer can output natively without falling back to "en-US".
# Other language codes are accepted but routed to the LLM with a one-line
# ``outputLanguage=...; pipeline may degrade`` notice in the response notes
# (Corti docs cap official support at ``en-US``).
ICODER_FACTS_NATIVE_LANGUAGES: frozenset[str] = frozenset({
    "en-US",
    "en-GB",
    "zh-CN",
    "zh-TW",
})


def default_output_language() -> str:
    """Default language when caller sends an empty string for ``outputLanguage``."""
    return "en-US"


# Server-side prompt pack — kept small so the cycle-1 endpoint stays
# focused on the wire-shape contract. Phase 1.2 cycle 2 (Streams) may
# share this template.
FACTSR_SYSTEM_PROMPT_EN = (
    "You are iCoDer FactsR™ (Phase 1.2 cycle 1). Extract structured clinical "
    "facts from the supplied text. For every fact you find, emit a JSON "
    "object with three keys: 'group' (one of the canonical Corti clinical "
    "category keys — e.g. chief-complaint, history-of-present-illness, "
    "vital-signs, past-medical-history, imaging-results, assessment, "
    "actions, demographics), 'text' (a short natural-language phrasing), "
    "and 'value' (a concise structured value — equal to text for free-form "
    "findings, normalised for vital-signs / lab-results). Output language "
    "must match ``outputLanguage``. Return only valid JSON; do NOT wrap in "
    "markdown fences."
)
