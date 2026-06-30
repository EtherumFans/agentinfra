"""iCoDer ``POST /api/v2/tools/extract-facts`` — Corti §3.2 / §13.4 FactsR™ parity.

Phase 1.2 cycle 1 (2026-06-30): the first GA endpoint of the Corti §13.4 Text
Generation family (``Streams`` WSS + ``FactsR`` REST). Bridges iCoDer's
text-generation surface to the documented Corti contract at
``api.eu.corti.app/v2/tools/extract-facts`` (captured in
``docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json``).

**What this endpoint is**
- A thin HTTP wrapper around ``llm_service.chat`` that extracts structured
  clinical facts (Corti kebab-case ``group`` taxonomy) from supplied text and
  projects the model output to the Corti ``{facts, outputLanguage, usageInfo}``
  shape.

**What this endpoint is NOT**
- NOT a replacement for the legacy ``/api/facts/extract`` (iCoDer Chinese-schema
  ``chief_complaint / diagnosis_facts / drug_facts / ...`` surface). The legacy
  endpoint stays; its wire-shape differs from Corti and is out of scope here.
- NOT yet OAuth-scoped (``facts`` capability scope wiring lands with the Phase
  1.2 OAuth client integration).

Field mapping (Corti ↔ iCoDer) is documented in
``docs/PHASE_1_2_FACTSR_FACTS_EXTRACTION.md``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.v2_tools_facts import (
    FACTSR_SYSTEM_PROMPT_EN,
    FactExtractResponse,
    FactItem,
    FactsExtractRequest,
    FactUsageInfo,
    ICODER_FACTS_NATIVE_LANGUAGES,
    default_output_language,
)
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Credit estimation ───────────────────────────────────────────────
# Corti bills ``usageInfo.creditsConsumed`` per inference (~0.011 in the
# captured sample). iCoDer derives a best-effort estimate from token usage
# when the provider returns it; otherwise it falls back to 0.0 so the
# response shape stays valid (never a 5xx for a missing usage block).
_CREDITS_PER_1K_TOKENS: float = 0.01


def _estimate_credits(usage: Any) -> float:
    """Map provider token usage → Corti-style ``creditsConsumed`` (>= 0.0)."""
    if not isinstance(usage, dict):
        return 0.0
    total = usage.get("total_tokens")
    if total is None:
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        total = prompt + completion
    try:
        return round(max(0.0, float(total) / 1000.0 * _CREDITS_PER_1K_TOKENS), 6)
    except (TypeError, ValueError):
        return 0.0


# ─── Output parsing ──────────────────────────────────────────────────


def _strip_code_fence(text: str) -> str:
    """Remove a leading/trailing markdown code fence if the model wrapped JSON."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        t = "\n".join(lines[1:]) if len(lines) > 1 else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _parse_facts(raw: str) -> list[FactItem]:
    """Parse the LLM JSON output into ``FactItem`` list.

    Accepts either a bare ``[ {...}, ... ]`` array or an object with a
    ``facts`` key. Unknown / malformed entries are dropped silently so a
    single bad row never fails the whole request. ``group`` values are
    forwarded as-is (no membership check against ``CORTI_FACT_GROUPS``) so
    domain-specific or future groups don't get dropped.
    """
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("facts", [])
    if not isinstance(parsed, list):
        return []

    facts: list[FactItem] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        group = str(row.get("group", "") or "").strip()
        text = str(row.get("text", "") or "").strip()
        value = str(row.get("value", "") or "").strip()
        if not text and not value:
            continue
        facts.append(FactItem(group=group, text=text, value=value or text))
    return facts


# ─── Endpoint ────────────────────────────────────────────────────────


@router.post("/extract-facts", response_model=FactExtractResponse)
@router.post("/extract-facts/", response_model=FactExtractResponse)
async def post_v2_tools_extract_facts(
    body: FactsExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """Corti §3.2 FactsR™ parity endpoint.

    Extracts structured clinical facts from ``context[]`` text blocks and
    returns them under the Corti ``{facts, outputLanguage, usageInfo}``
    envelope. Authentication is via session JWT (consistent with the v2
    coding endpoint); OAuth ``facts`` capability scope lands in a later
    Phase 1.2 cycle.
    """
    # ── 1. Hospital-pilot gate (don't fake-model in production) ─────────
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": "llm_credential_missing",
                    "hint": (
                        "Set ICODER_CREDENTIAL_LLM (DeepSeek API key) before calling "
                        "/api/v2/tools/extract-facts. Set ICODER_ALLOW_DEGRADED_NO_KEY=1 "
                        "ONLY for local dev."
                    ),
                },
            )

    # ── 2. Validate context; fail fast on empty input ──────────────────
    if not body.context or not any(item.text.strip() for item in body.context):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "empty_context",
                "hint": "context[].text must contain at least one non-empty string",
            },
        )

    # ── 3. Resolve output language (echo; degrade-with-notice off-list) ─
    out_lang = body.outputLanguage or default_output_language()
    blocks = [c.text for c in body.context if c.text and c.text.strip()]
    merged = "\n\n".join(blocks)

    system_prompt = FACTSR_SYSTEM_PROMPT_EN
    if out_lang not in ICODER_FACTS_NATIVE_LANGUAGES:
        system_prompt = (
            f"{system_prompt}\n\n(outputLanguage={out_lang}; not an officially "
            "supported language — pipeline may degrade. Best-effort output.)"
        )
    else:
        system_prompt = f"{system_prompt}\n\noutputLanguage={out_lang}."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": merged},
    ]

    # ── 4. PII redaction (best-effort; never blocks) ───────────────────
    try:
        from app.main import app as _app
        _data_policy = getattr(_app.state, "data_policy", None) if _app else None
    except Exception:
        _data_policy = None
    if _data_policy is not None and getattr(_data_policy, "pii_redaction_required", False):
        try:
            from icoder_runtime.core.pii_redaction import PIIRedactor
            redactor = PIIRedactor(enabled=True)
            messages, _ = redactor.redact_messages(messages)
        except Exception as _pii_err:
            logger.warning(f"PII redaction skipped (non-fatal): {_pii_err!r}")

    # ── 5. Run the extraction inference ────────────────────────────────
    try:
        result = await llm_service.chat(messages=messages, temperature=0.0, max_tokens=2048)
    except Exception as exc:
        logger.error(f"/api/v2/tools/extract-facts llm_service.chat failed: {exc!r}")
        raise HTTPException(
            status_code=502,
            detail={"error": "facts_extraction_failed", "reason": str(exc)[:200]},
        )

    content = result.get("content", "") if isinstance(result, dict) else ""
    usage = result.get("usage", None) if isinstance(result, dict) else None

    # ── 6. Corti-shape projection ──────────────────────────────────────
    facts = _parse_facts(content)
    return FactExtractResponse(
        facts=facts,
        outputLanguage=out_lang,
        usageInfo=FactUsageInfo(creditsConsumed=_estimate_credits(usage)),
    )


# ─── Phase 1.3 cycle 13 — Facts LIST (Corti §13.5) ──────────────────
# Spec source: ``docs/corti-reverse-engineered/facts-list-facts.md``
# (6,314B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/list-facts.md``).
#
# This is the **first endpoint of the §13.5 Facts family** (5 more to
# follow: add-facts, list-fact-groups, update-fact, update-facts).
# Distinct from Phase 1.2 cycle 1 §3.2/§13.4 extract-facts (LLM call) —
# list-facts is a CRUD-style read of stored facts.
#
# **Stub strategy** (no DB):
#   - ``empty-{uuid}`` interaction_id → ``facts: []`` (exercises the
#     empty envelope path)
#   - default → 2 facts with mixed group/source (core + system) and
#     evidence with reference/quote echoed from interaction_id prefix.
#   - ``facts[*].id`` and ``facts[*].groupId`` echo interaction_id so
#     SDK callers can verify the path-echo contract.

from app.schemas.v2_tools_facts import (
    FactsEvidence,
    FactsListItem,
    FactsListResponse,
)


def _stub_facts_for_interaction(interaction_id: str) -> List[FactsListItem]:
    """Deterministic stub data per interaction UUID.

    Returns ``[]`` when interaction_id starts with ``empty-`` so callers
    can verify the spec's empty-envelope path. Otherwise returns 2 facts
    with mixed ``source`` and ``group`` values, each with one evidence
    row whose ``reference`` and ``quote`` echo the interaction_id.
    """
    if interaction_id.startswith("empty-"):
        return []

    # Derive a deterministic short tag from interaction_id so tests can
    # assert path-echo without hard-coding UUIDs.
    short_tag = interaction_id.replace("-", "")[:12]
    ts = "2026-07-01T12:00:00Z"
    return [
        FactsListItem(
            id=f"{interaction_id}-fact-{short_tag}-01",
            text="67-year-old male presenting with recurrent chest tightness.",
            group="demographics",
            groupId=f"{interaction_id}-grp-{short_tag}-01",
            isDiscarded=False,
            source="core",
            createdAt=ts,
            updatedAt=ts,
            evidence=[
                FactsEvidence(
                    type="transcript",
                    reference=f"/interactions/{interaction_id}/transcripts/{short_tag}",
                    quote="67-year-old male, recurrent chest tightness for 3 days.",
                ),
            ],
        ),
        FactsListItem(
            id=f"{interaction_id}-fact-{short_tag}-02",
            text="LVEF 38% on echocardiogram (2026-06-28).",
            group="imaging-results",
            groupId=f"{interaction_id}-grp-{short_tag}-02",
            isDiscarded=False,
            source="system",
            createdAt=ts,
            updatedAt=ts,
            evidence=[
                FactsEvidence(
                    type="report",
                    reference=f"/interactions/{interaction_id}/recordings/{short_tag}",
                    quote="LVEF 38%; mild mitral regurgitation.",
                ),
            ],
        ),
    ]


@router.get("/interactions/{interaction_id}/facts", response_model=FactsListResponse)
@router.get("/interactions/{interaction_id}/facts/", response_model=FactsListResponse)
async def get_v2_tools_interaction_facts(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
):
    """Corti §13.5 facts_list — list facts for an interaction.

    Spec: ``GET /interactions/{id}/facts/`` (operationId ``facts_list``).
    Path: ``/api/v2/tools/interactions/{interaction_id}/facts/`` (mounted
    under the existing ``/api/v2/tools`` prefix).

    Returns a ``{facts: [...]}`` envelope. Stub does NOT hit a DB —
    ``empty-{uuid}`` interaction IDs return an empty list; all other
    IDs return 2 deterministic facts whose ``id``/``groupId``/``reference``
    echo the interaction_id (path-echo contract).

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    facts = _stub_facts_for_interaction(interaction_id)
    return FactsListResponse(facts=facts)


# ─── Phase 1.3 cycle 14 — Facts ADD (Corti §13.5) ──────────────────
# Spec source: ``docs/corti-reverse-engineered/facts-add-facts.md``
# (7,143B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/add-facts.md``).
#
# This is the **second endpoint of the §13.5 Facts family** (4 more to
# follow). Distinct from Phase 1.2 cycle 1 §3.2/§13.4 extract-facts
# (LLM call) — add-facts is a CRUD-style create where the caller
# supplies the fact text+group; iCoDer just echoes back the created
# facts with deterministic server-assigned ids and timestamps.
#
# **Stub strategy** (no DB):
#   - Echoes each input fact back with server-assigned
#     ``id``/``groupId``/``updatedAt`` (deterministic per interaction_id).
#   - ``source`` defaults to ``"user"`` when caller omits it (per spec,
#     source is optional).
#   - ``isDiscarded`` defaults to ``False`` on every create.

from app.schemas.v2_tools_facts import (
    FactsCreateItem,
    FactsCreateRequest,
    FactsCreateResponse,
)


def _stub_create_facts(
    interaction_id: str, body: FactsCreateRequest
) -> List[FactsCreateItem]:
    """Echo input facts back with deterministic server-assigned ids.

    Each returned fact mirrors the input ``text``/``group``/``source``
    and adds server-assigned ``id``/``groupId``/``updatedAt``. Path
    UUIDs are echoed so SDK callers can verify the contract.
    """
    short_tag = interaction_id.replace("-", "")[:12]
    ts = "2026-07-01T12:00:00Z"
    out: List[FactsCreateItem] = []
    for i, fact_in in enumerate(body.facts, start=1):
        idx = f"{i:02d}"
        out.append(
            FactsCreateItem(
                id=f"{interaction_id}-fact-{short_tag}-{idx}",
                text=fact_in.text,
                group=fact_in.group,
                groupId=f"{interaction_id}-grp-{short_tag}-{idx}",
                source=fact_in.source or "user",
                isDiscarded=False,
                updatedAt=ts,
            )
        )
    return out


@router.post("/interactions/{interaction_id}/facts", response_model=FactsCreateResponse)
@router.post("/interactions/{interaction_id}/facts/", response_model=FactsCreateResponse)
async def post_v2_tools_interaction_facts(
    interaction_id: str,
    body: FactsCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Corti §13.5 facts_create — add facts to an interaction.

    Spec: ``POST /interactions/{id}/facts/`` (operationId ``facts_create``).
    Path: ``/api/v2/tools/interactions/{interaction_id}/facts/`` (mounted
    under the existing ``/api/v2/tools`` prefix).

    Request body: ``{facts: [{text, group, source?}, ...]}``.
    Response: ``{facts: [{id, text, group, groupId, source, isDiscarded, updatedAt}, ...]}``.

    Stub does NOT persist (no DB). Each input fact is echoed back with
    deterministic server-assigned ``id``/``groupId``/``updatedAt`` and
    ``isDiscarded=False``.

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    facts = _stub_create_facts(interaction_id, body)
    return FactsCreateResponse(facts=facts)
