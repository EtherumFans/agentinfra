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

from pydantic import BaseModel, Field, field_validator, model_validator


MAX_FACTS_CONTEXT_CHARS = 200_000


# ─── Request ──────────────────────────────────────────────────────────


class FactsContextItem(BaseModel):
    """One block of source text the model should consider for fact extraction.

    Mirrors ``context[]`` in ``/api/icoder/coding-review-v2`` (Phase 1.1)
    and the canonical Corti shape. ``type`` is a free-form discriminator
    (today only ``text`` is wired); iCoDer keeps the field so future audio
    transcriptions can be fed without breaking the wire format.
    """
    text: str = Field(default="", max_length=MAX_FACTS_CONTEXT_CHARS, description="Source text to extract facts from")
    type: str = Field(default="text", max_length=64, description="Modality discriminator: text (today); audio reserved for Phase 1.3")


class FactsExtractRequest(BaseModel):
    """Corti §3.2 ``POST /v2/tools/extract-facts`` request body."""
    context: List[FactsContextItem] = Field(
        default_factory=list,
        max_length=64,
        description="One or more context blocks (text spans). At least one must contain non-whitespace text.",
    )
    outputLanguage: str = Field(
        default="en-US",
        max_length=35,
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

    @model_validator(mode="after")
    def _limit_total_context(self):
        total_chars = sum(len(item.text) for item in self.context)
        if total_chars > MAX_FACTS_CONTEXT_CHARS:
            raise ValueError(
                f"context text exceeds {MAX_FACTS_CONTEXT_CHARS} characters"
            )
        return self


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


# ─── Phase 1.3 cycle 13 — Facts LIST (Corti §13.5) ──────────────────
# Spec source: ``docs/corti-reverse-engineered/facts-list-facts.md``
# (6,314B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/list-facts.md``).
#
# This is the first endpoint of the §13.5 Facts family (5 more to follow:
# add-facts, list-fact-groups, update-fact, update-facts). Note this is
# **distinct** from the Phase 1.2 cycle 1 §3.2/§13.4 extract-facts (LLM
# call) — list-facts is a CRUD-style read of stored facts.


from datetime import datetime
from typing import List as _List


class FactsEvidence(BaseModel):
    """A piece of evidence that supports a fact.

    Mirrors ``FactsEvidence`` in
    ``docs/corti-reverse-engineered/facts-list-facts.md``.
    """
    type: Optional[str] = Field(default=None, description="The category of evidence")
    reference: Optional[str] = Field(default=None, description="A reference that supports the fact")
    quote: Optional[str] = Field(
        default=None,
        description="A direct excerpt or phrase extracted from the reference source that justifies the fact",
    )


class FactsListItem(BaseModel):
    """One fact in the ``facts[]`` array.

    All fields are optional in the spec — every fact can be partially
    populated. iCoDer mirrors the spec exactly (no extra required fields).
    """
    id: Optional[str] = Field(default=None, description="The unique identifier of the fact (UUID)")
    text: Optional[str] = Field(default=None, description="The text content of the fact")
    group: Optional[str] = Field(default=None, description="The key identifying the group the fact belongs to")
    groupId: Optional[str] = Field(default=None, description="The unique identifier of the group")
    isDiscarded: Optional[bool] = Field(
        default=None,
        description="Whether the fact has been marked as discarded by an end-user",
    )
    source: Optional[str] = Field(
        default=None,
        description="Source: 'core' (LLM-generated), 'user' (added by user), 'system' (e.g. EHR)",
    )
    createdAt: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the fact was created")
    updatedAt: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the fact was last updated")
    evidence: _List[FactsEvidence] = Field(default_factory=list, description="Evidence supporting the fact")


class FactsListResponse(BaseModel):
    """Response shape for ``GET /interactions/{id}/facts/``.

    Mirrors ``FactsListResponse`` in
    ``docs/corti-reverse-engineered/facts-list-facts.md``. ``facts`` is
    the **only** required field per spec.
    """
    facts: _List[FactsListItem] = Field(
        default_factory=list,
        description="A list of facts associated with the interaction",
    )


# ─── Phase 1.3 cycle 14 — Facts ADD (Corti §13.5) ──────────────────
# Spec source: ``docs/corti-reverse-engineered/facts-add-facts.md``
# (7,143B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/add-facts.md``).
#
# This is the **second endpoint of the §13.5 Facts family** (4 more to
# follow: list-fact-groups, update-fact, update-facts). Distinct from
# Phase 1.2 cycle 1 §3.2/§13.4 extract-facts (LLM call) — add-facts is a
# CRUD-style create where the caller supplies the fact text+group.


class FactsCreateInput(BaseModel):
    """One fact in the ``facts[]`` create payload.

    Per spec (``FactsCreateInput`` in
    ``docs/corti-reverse-engineered/facts-add-facts.md``), ``text`` and
    ``group`` are **required**; ``source`` is optional (enum
    core|system|user; iCoDer defaults caller-created facts to
    ``user`` since the caller is the one creating it).
    """
    text: str = Field(default="", description="The text content of the fact")
    group: str = Field(default="other", description="The key identifying the group the fact belongs to")
    source: Optional[str] = Field(
        default="user",
        description="Source: 'core' (LLM), 'user' (added by user), 'system' (e.g. EHR)",
    )


class FactsCreateRequest(BaseModel):
    """Request shape for ``POST /interactions/{id}/facts/``.

    Per spec (``FactsCreateRequest``), ``facts`` is **required** (array
    of ``FactsCreateInput``).
    """
    facts: _List[FactsCreateInput] = Field(
        default_factory=list,
        description="A list of facts to be created",
    )


class FactsCreateItem(BaseModel):
    """One fact in the ``facts[]`` create response.

    All fields are optional in the spec (the server may or may not
    populate them). iCoDer mirrors the spec exactly.
    """
    id: Optional[str] = Field(default=None, description="The unique identifier of the newly created fact (UUID)")
    text: Optional[str] = Field(default=None, description="The textual content of the created fact")
    group: Optional[str] = Field(default=None, description="The group key categorizing the fact")
    groupId: Optional[str] = Field(default=None, description="The unique identifier of the group")
    source: Optional[str] = Field(
        default=None,
        description="Source: 'core' (LLM), 'user' (added by user), 'system' (e.g. EHR)",
    )
    isDiscarded: Optional[bool] = Field(
        default=None,
        description="Whether the fact has been marked as discarded by an end-user",
    )
    updatedAt: Optional[str] = Field(default=None, description="ISO 8601 timestamp when the fact was last updated")


class FactsCreateResponse(BaseModel):
    """Response shape for ``POST /interactions/{id}/facts/``.

    Per spec (``FactsCreateResponse``), ``facts`` is **required**.
    """
    facts: _List[FactsCreateItem] = Field(
        default_factory=list,
        description="A list of successfully created facts",
    )


# ─── Phase 1.3 cycle 15 — Facts LIST-FACT-GROUPS (Corti §13.5) ─────
# Spec source: ``docs/corti-reverse-engineered/facts-list-fact-groups.md``
# (4,552B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/list-fact-groups.md``).
#
# **This is a GLOBAL endpoint, NOT path-scoped to an interaction.**
# Path: ``GET /factgroups/`` (no ``/interactions/{id}/...`` prefix).
# In iCoDer: ``GET /api/v2/tools/factgroups/`` (under the existing
# ``/api/v2/tools`` prefix).
#
# Returns the **catalog of fact-group keys** the platform supports
# (e.g. demographics, chief-complaint, vital-signs, ...). iCoDer
# reuses the canonical ``CORTI_FACT_GROUPS`` frozenset already defined
# in this module and projects those keys into the
# ``{data: [...]}`` envelope with deterministic per-group UUIDs.


class FactsFactGroupsItemTranslation(BaseModel):
    """One translation row inside ``FactsFactGroupsItem.translations[]``.

    Per spec, all fields are optional (server may not populate any of
    them). iCoDer mirrors the spec exactly.
    """
    id: Optional[int] = Field(default=None, description="Translation id (integer)")
    languages_id: Optional[str] = Field(default=None, description="Language identifier (e.g. 'en-US')")
    name: Optional[str] = Field(default=None, description="Localized display name of the fact group")


class FactsFactGroupsItem(BaseModel):
    """One fact-group entry in the ``data[]`` array.

    Per spec, all fields are optional. iCoDer mirrors the spec exactly.
    """
    id: Optional[str] = Field(default=None, description="UUID of the fact group")
    key: Optional[str] = Field(default=None, description="Kebab-case key identifying the group (e.g. 'demographics')")
    translations: _List[FactsFactGroupsItemTranslation] = Field(
        default_factory=list,
        description="Per-language display names for this group",
    )


class FactsFactGroupsListResponse(BaseModel):
    """Response shape for ``GET /factgroups/``.

    Per spec (``FactsFactGroupsListResponse``), ``data`` is **required**
    (array of ``FactsFactGroupsItem``). The envelope uses ``data``
    (not ``factGroups``) per the Corti contract.
    """
    data: _List[FactsFactGroupsItem] = Field(
        default_factory=list,
        description="A list of available fact groups",
    )


# ─── Phase 1.3 cycle 16 — Facts UPDATE (Corti §13.5) ───────────────
# Spec source: ``docs/corti-reverse-engineered/facts-update-fact.md``
# (6,927B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/update-fact.md``).
#
# This is the **fourth endpoint of the §13.5 Facts family** (2 more to
# follow: update-facts batch). Distinct from add-facts (cycle 14) — this
# is PATCH (in-place update) of an existing fact.


class FactsUpdateRequest(BaseModel):
    """Request shape for ``PATCH /interactions/{id}/facts/{factId}``.

    Per spec (``FactsUpdateRequest``), all 4 fields are **optional**
    (PATCH semantics — caller sends only what they want to change).
    iCoDer honors the spec exactly: a request with an empty body is
    valid (no-op).
    """
    text: Optional[str] = Field(default=None, description="The updated text of the fact")
    group: Optional[str] = Field(default=None, description="The updated group key for the fact")
    source: Optional[str] = Field(
        default=None,
        description="The updated source ('core'/'user'/'system')",
    )
    isDiscarded: Optional[bool] = Field(
        default=None,
        description="Set to true to mark the fact as discarded by an end-user",
    )


class FactsUpdateResponse(BaseModel):
    """Response shape for ``PATCH /interactions/{id}/facts/{factId}``.

    Per spec (``FactsUpdateResponse``), **all 8 fields are required**:
    id, text, group, groupId, source, isDiscarded, createdAt, updatedAt.
    This is stricter than add-facts (cycle 14) where the response fields
    were all optional. iCoDer honors the spec exactly.
    """
    id: str = Field(..., description="The unique identifier of the fact (UUID)")
    text: str = Field(..., description="The (possibly updated) text content of the fact")
    group: str = Field(..., description="The (possibly updated) group key")
    groupId: str = Field(..., description="The unique identifier of the associated group (UUID)")
    source: str = Field(..., description="The (possibly updated) source")
    isDiscarded: bool = Field(..., description="Whether the fact is marked as discarded")
    createdAt: str = Field(..., description="ISO 8601 timestamp when the fact was originally created")
    updatedAt: str = Field(..., description="ISO 8601 timestamp when the fact was last updated")


# ─── Phase 1.3 cycle 17 — Facts UPDATE-FACTS BATCH (Corti §13.5) ──
# Spec source: ``docs/corti-reverse-engineered/facts-update-facts.md``
# (7,424B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/update-facts.md``).
#
# This is the **fifth endpoint of the §13.5 Facts family** (1 more to
# follow). Distinct from update-fact (cycle 16):
# - Path is **trailing-slash collection** ``/interactions/{id}/facts/``
#   (vs single-resource PATCH ``/interactions/{id}/facts/{factId}``).
# - Request wraps in ``{facts: [...]}`` (vs bare object for single).
# - **NO ``source`` field in batch request** (per spec — only factId,
#   text, group, isDiscarded are updateable via batch). The single
#   update-fact (cycle 16) does support source updates.


class FactsBatchUpdateInput(BaseModel):
    """One fact in the ``facts[]`` batch update payload.

    Per spec (``FactsBatchUpdateInput``), ``factId`` is **required**;
    ``text``, ``group``, ``isDiscarded`` are optional. **NO ``source``
    field** per spec (source is not updateable via batch).
    """
    factId: str = Field(..., description="The unique identifier of the fact to be updated (UUID)")
    text: Optional[str] = Field(default=None, description="The updated text content of the fact")
    group: Optional[str] = Field(default=None, description="The updated group key for the fact")
    isDiscarded: Optional[bool] = Field(
        default=None,
        description="Set to true to mark the fact as discarded",
    )


class FactsBatchUpdateRequest(BaseModel):
    """Request shape for ``PATCH /interactions/{id}/facts/``.

    Per spec (``FactsBatchUpdateRequest``), ``facts`` is **required**
    (array of ``FactsBatchUpdateInput``).
    """
    facts: _List[FactsBatchUpdateInput] = Field(
        default_factory=list,
        description="A list of facts to be updated",
    )


class FactsBatchUpdateItem(BaseModel):
    """One fact in the ``facts[]`` batch update response.

    Per spec (``FactsBatchUpdateItem``), all 8 fields are required:
    id, text, group, groupId, source, isDiscarded, createdAt, updatedAt.
    Same shape as cycle 16's ``FactsUpdateResponse``.
    """
    id: str = Field(..., description="The unique identifier of the updated fact (UUID)")
    text: str = Field(..., description="The (possibly updated) text content of the fact")
    group: str = Field(..., description="The (possibly updated) group key")
    groupId: str = Field(..., description="The unique identifier of the associated group (UUID)")
    source: str = Field(..., description="The (possibly updated) source")
    isDiscarded: bool = Field(..., description="Whether the fact is marked as discarded")
    createdAt: str = Field(..., description="ISO 8601 timestamp when the fact was originally created")
    updatedAt: str = Field(..., description="ISO 8601 timestamp when the fact was last updated")


class FactsBatchUpdateResponse(BaseModel):
    """Response shape for ``PATCH /interactions/{id}/facts/``.

    Per spec (``FactsBatchUpdateResponse``), ``facts`` is **required**
    (array of ``FactsBatchUpdateItem``).
    """
    facts: _List[FactsBatchUpdateItem] = Field(
        default_factory=list,
        description="A list of successfully updated facts",
    )
