"""iCoDer ``POST /api/v2/tools/extract-facts`` — Corti §3.2 / §13.4 FactsR™ parity.

Phase 1.2 cycle 1 (2026-06-30): the first GA endpoint of the Corti §13.4 Text
Generation family (``Streams`` WSS + ``FactsR`` REST). Bridges iCoDer's
text-generation surface to the documented Corti contract at
``api.eu.corti.app/v2/tools/extract-facts`` (captured in
``docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json``).

**What this endpoint is**
- A thin HTTP wrapper around the canonical ``LLMGateway`` that extracts structured
  clinical facts (Corti kebab-case ``group`` taxonomy) from supplied text and
  projects the model output to the Corti ``{facts, outputLanguage, usageInfo}``
  shape.

**What this endpoint is NOT**
- NOT a replacement for the legacy ``/api/facts/extract`` (iCoDer Chinese-schema
  ``chief_complaint / diagnosis_facts / drug_facts / ...`` surface). The legacy
  endpoint stays; its wire-shape differs from Corti and is out of scope here.
- Authenticated through the shared user/tenant boundary; a mock or degraded
  provider is never promoted as clinical output.

Field mapping (Corti ↔ iCoDer) is documented in
``docs/PHASE_1_2_FACTSR_FACTS_EXTRACTION.md``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
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
from app.services.clinical_fact_repository import clinical_fact_repository
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


def _fact_scope(
    current_user: User,
    current_org: Organization,
    interaction_id: str,
) -> dict[str, str]:
    interaction_id = interaction_id.strip()
    organization_id = str(getattr(current_org, "id", "") or "")
    owner_id = str(getattr(current_user, "id", "") or "")
    if not interaction_id or len(interaction_id) > 160:
        raise HTTPException(status_code=400, detail="interaction_id_invalid")
    if not organization_id or not owner_id:
        raise HTTPException(status_code=403, detail="organization_context_required")
    return {
        "organization_id": organization_id,
        "owner_id": owner_id,
        "interaction_id": interaction_id,
    }


def _validate_fact_fields(text: str, group: str, source: str) -> tuple[str, str, str]:
    text = (text or "").strip()
    group = (group or "").strip()
    source = (source or "").strip().casefold()
    if not text or len(text) > 4000:
        raise HTTPException(status_code=422, detail="fact_text_invalid")
    if not group or len(group) > 96:
        raise HTTPException(status_code=422, detail="fact_group_invalid")
    if source not in {"core", "system", "user"}:
        raise HTTPException(status_code=422, detail="fact_source_invalid")
    return text, group, source


def _iso(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z")


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
        prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
        completion = usage.get(
            "completion_tokens", usage.get("output_tokens", 0)
        ) or 0
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
        raise ValueError("facts_provider_content_empty")
    try:
        parsed = json.loads(_strip_code_fence(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("facts_provider_json_invalid") from exc
    if isinstance(parsed, dict):
        if "facts" not in parsed:
            raise ValueError("facts_provider_contract_invalid")
        parsed = parsed["facts"]
    if not isinstance(parsed, list):
        raise ValueError("facts_provider_contract_invalid")

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
    if parsed and not facts:
        raise ValueError("facts_provider_rows_invalid")
    return facts


async def _invoke_facts_model(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Use the canonical gateway and reject all mock/degraded fallbacks."""
    from app.main import app as application

    gateway = getattr(application.state, "platform_gateway", None)
    if gateway is None:
        raise RuntimeError("platform_gateway_unavailable")
    result = await gateway.generate(
        messages,
        response_schema={
            "type": "object",
            "required": ["facts"],
            "properties": {"facts": {"type": "array"}},
        },
        context={"operation": "corti_extract_facts", "clinical": True},
    )
    if not isinstance(result, dict):
        raise RuntimeError("facts_provider_response_invalid")
    if result.get("degraded") is True or result.get("is_mock") is True:
        raise RuntimeError("facts_provider_degraded")
    return result


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
            logger.error(
                "facts PHI redaction failed error_type=%s",
                type(_pii_err).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail={"error": "phi_redaction_failed"},
            ) from _pii_err

    # ── 5. Run the extraction inference ────────────────────────────────
    try:
        result = await _invoke_facts_model(messages)
    except Exception as exc:
        logger.error(
            "/api/v2/tools/extract-facts gateway failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "facts_extraction_failed", "reason": str(exc)[:200]},
        ) from exc

    content = result.get("content", "") if isinstance(result, dict) else ""
    usage = result.get("usage", None) if isinstance(result, dict) else None

    # ── 6. Corti-shape projection ──────────────────────────────────────
    try:
        facts = _parse_facts(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "facts_response_invalid", "reason": str(exc)},
        ) from exc
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
# Facts are read from encrypted, tenant/principal-scoped durable storage.
# Unknown interactions return an empty envelope and never synthesize rows.

from app.schemas.v2_tools_facts import (
    FactsEvidence,
    FactsListItem,
    FactsListResponse,
)


def _fact_list_item(row: Any) -> FactsListItem:
    evidence = [
        FactsEvidence.model_validate(item)
        for item in clinical_fact_repository.evidence(row)
        if isinstance(item, dict)
    ]
    return FactsListItem(
        id=row.fact_id,
        text=clinical_fact_repository.text(row),
        group=row.group_key,
        groupId=row.group_id,
        isDiscarded=row.is_discarded,
        source=row.source,
        createdAt=_iso(row.created_at),
        updatedAt=_iso(row.updated_at),
        evidence=evidence,
    )


@router.get("/interactions/{interaction_id}/facts", response_model=FactsListResponse)
@router.get("/interactions/{interaction_id}/facts/", response_model=FactsListResponse)
async def get_v2_tools_interaction_facts(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti §13.5 facts_list — list facts for an interaction.

    Spec: ``GET /interactions/{id}/facts/`` (operationId ``facts_list``).
    Path: ``/api/v2/tools/interactions/{interaction_id}/facts/`` (mounted
    under the existing ``/api/v2/tools`` prefix).

    Returns the durable, encrypted and tenant/principal-scoped facts for the
    interaction. Unknown interactions return an empty list.

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    rows = await clinical_fact_repository.list(
        db,
        **_fact_scope(current_user, current_org, interaction_id),
    )
    return FactsListResponse(facts=[_fact_list_item(row) for row in rows])


# ─── Phase 1.3 cycle 14 — Facts ADD (Corti §13.5) ──────────────────
# Spec source: ``docs/corti-reverse-engineered/facts-add-facts.md``
# (7,143B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/add-facts.md``).
#
# This is the **second endpoint of the §13.5 Facts family** (4 more to
# follow). Distinct from Phase 1.2 cycle 1 §3.2/§13.4 extract-facts
# (LLM call) — add-facts is a CRUD-style create where the caller
# supplies the fact text+group; iCoDer persists the created facts with
# opaque server-assigned ids and timestamps.
#
# **Persistence semantics**:
#   - Returns each newly stored fact with server-assigned
#     ``id``/``groupId``/``updatedAt``.
#   - ``source`` defaults to ``"user"`` when caller omits it (per spec,
#     source is optional).
#   - ``isDiscarded`` defaults to ``False`` on every create.

from app.schemas.v2_tools_facts import (
    FactsCreateItem,
    FactsCreateRequest,
    FactsCreateResponse,
)


def _fact_create_item(row: Any) -> FactsCreateItem:
    return FactsCreateItem(
        id=row.fact_id,
        text=clinical_fact_repository.text(row),
        group=row.group_key,
        groupId=row.group_id,
        source=row.source,
        isDiscarded=row.is_discarded,
        updatedAt=_iso(row.updated_at),
    )


@router.post("/interactions/{interaction_id}/facts", response_model=FactsCreateResponse)
@router.post("/interactions/{interaction_id}/facts/", response_model=FactsCreateResponse)
async def post_v2_tools_interaction_facts(
    interaction_id: str,
    body: FactsCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti §13.5 facts_create — add facts to an interaction.

    Spec: ``POST /interactions/{id}/facts/`` (operationId ``facts_create``).
    Path: ``/api/v2/tools/interactions/{interaction_id}/facts/`` (mounted
    under the existing ``/api/v2/tools`` prefix).

    Request body: ``{facts: [{text, group, source?}, ...]}``.
    Response: ``{facts: [{id, text, group, groupId, source, isDiscarded, updatedAt}, ...]}``.

    Facts are persisted with tenant/principal scope and encrypted text.

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    if len(body.facts) > 100:
        raise HTTPException(status_code=422, detail="facts_count_invalid")
    scope = _fact_scope(current_user, current_org, interaction_id)
    rows = []
    for fact in body.facts:
        text, group, source = _validate_fact_fields(
            fact.text,
            fact.group,
            fact.source or "user",
        )
        rows.append(await clinical_fact_repository.create(
            db,
            **scope,
            text=text,
            group_key=group,
            source=source,
        ))
    return FactsCreateResponse(facts=[_fact_create_item(row) for row in rows])


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
# in ``app.schemas.v2_tools_facts`` and projects those
# keys into the ``{data: [...]}`` envelope with deterministic
# per-group UUIDs (uuid5 from a fixed namespace + key).

from app.schemas.v2_tools_facts import (
    CORTI_FACT_GROUPS,
    FactsFactGroupsItem,
    FactsFactGroupsItemTranslation,
    FactsFactGroupsListResponse,
)


def _fact_groups_catalog() -> List[FactsFactGroupsItem]:
    """Build the stable fact-group catalog from ``CORTI_FACT_GROUPS``.

    Each group gets a stable UUID5 derived from a fixed namespace and
    the kebab-case key, plus a single en-US translation row with the
    key as the display name. Stable across calls so SDK callers can
    cache the response.
    """
    import uuid as _uuid

    # Fixed namespace UUID — same across all iCoDer deployments so the
    # generated group ids are stable and SDKs can cache them.
    NS = _uuid.UUID("5b3d4f7e-1c2a-4b8d-9e6f-0a1b2c3d4e5f")
    out: List[FactsFactGroupsItem] = []
    for key in sorted(CORTI_FACT_GROUPS):
        out.append(
            FactsFactGroupsItem(
                id=str(_uuid.uuid5(NS, f"icoder.factgroup.{key}")),
                key=key,
                translations=[
                    FactsFactGroupsItemTranslation(
                        id=1,
                        languages_id="en-US",
                        name=key,
                    ),
                ],
            )
        )
    return out


@router.get("/factgroups", response_model=FactsFactGroupsListResponse)
@router.get("/factgroups/", response_model=FactsFactGroupsListResponse)
async def get_v2_tools_fact_groups(
    current_user: User = Depends(get_current_user),
):
    """Corti §13.5 facts_fact_groups_list — list the fact-group catalog.

    Spec: ``GET /factgroups/`` (operationId ``facts_fact_groups_list``).
    Path: ``/api/v2/tools/factgroups/`` (mounted under the existing
    ``/api/v2/tools`` prefix). **Not path-scoped to an interaction**
    — the catalog is global to the tenant.

    Response: ``{data: [{id, key, translations: [{id, languages_id, name}]}, ...]}``.
    The ``data`` field is required; individual item fields are all
    optional per spec.

    The catalog is deterministic — every call returns the same set of group
    rows derived from ``CORTI_FACT_GROUPS`` (17 keys at last count).
    Group UUIDs are uuid5 from a fixed namespace + kebab-case key, so
    SDK callers can cache them across requests.

    Error response per spec is **500** (RFC9457 ``ErrorResponse``) —
    note this differs from the 504 in list-facts/add-facts.
    """
    items = _fact_groups_catalog()
    return FactsFactGroupsListResponse(data=items)


# ─── Phase 1.3 cycle 16 — Facts UPDATE (Corti §13.5) ───────────────
# Spec source: ``docs/corti-reverse-engineered/facts-update-fact.md``
# (6,927B, fetched 2026-07-01 from
# ``https://docs.corti.ai/api-reference/facts/update-fact.md``).
#
# This is the **fourth endpoint of the §13.5 Facts family** (2 more to
# follow: update-facts batch). Distinct from add-facts (cycle 14) — this
# is PATCH (in-place update) of an existing fact.
#
# PATCH semantics update only fields present in the request. Missing or
# cross-scope fact ids return 404; omitted fields retain persisted values.

from app.schemas.v2_tools_facts import (
    FactsUpdateRequest,
    FactsUpdateResponse,
)


def _fact_update_response(row: Any) -> FactsUpdateResponse:
    return FactsUpdateResponse(
        id=row.fact_id,
        text=clinical_fact_repository.text(row),
        group=row.group_key,
        groupId=row.group_id,
        source=row.source,
        isDiscarded=row.is_discarded,
        createdAt=_iso(row.created_at),
        updatedAt=_iso(row.updated_at),
    )


@router.patch("/interactions/{interaction_id}/facts/{fact_id}", response_model=FactsUpdateResponse)
async def patch_v2_tools_interaction_fact(
    interaction_id: str,
    fact_id: str,
    body: FactsUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti §13.5 facts_update — update a single fact.

    Spec: ``PATCH /interactions/{id}/facts/{factId}`` (operationId
    ``facts_update``). Path: ``/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}``
    (mounted under the existing ``/api/v2/tools`` prefix).

    Request body: ``{text?, group?, source?, isDiscarded?}`` — all
    fields optional (PATCH semantics).
    Response: ``{id, text, group, groupId, source, isDiscarded, createdAt, updatedAt}``
    — all 8 fields **required** per spec.

    The update is persisted in encrypted, tenant/principal-scoped storage.
    Fields omitted from the PATCH body retain their existing values.

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    scope = _fact_scope(current_user, current_org, interaction_id)
    row = await clinical_fact_repository.get(db, **scope, fact_id=fact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="fact_not_found")
    if body.text is not None and (
        not body.text.strip() or len(body.text.strip()) > 4000
    ):
        raise HTTPException(status_code=422, detail="fact_text_invalid")
    if body.group is not None and (
        not body.group.strip() or len(body.group.strip()) > 96
    ):
        raise HTTPException(status_code=422, detail="fact_group_invalid")
    if body.source is not None and body.source.strip().casefold() not in {
        "core", "system", "user",
    }:
        raise HTTPException(status_code=422, detail="fact_source_invalid")
    row = await clinical_fact_repository.update(
        db,
        row,
        text=body.text.strip() if body.text is not None else None,
        group_key=body.group.strip() if body.group is not None else None,
        source=body.source.strip().casefold() if body.source is not None else None,
        is_discarded=body.isDiscarded,
    )
    return _fact_update_response(row)


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
#   text, group, isDiscarded are updateable via batch).
#
# Batch updates validate the full request before mutation, reject duplicate or
# missing fact ids, and preserve each row's source (not mutable in this shape).

from app.schemas.v2_tools_facts import (
    FactsBatchUpdateItem,
    FactsBatchUpdateRequest,
    FactsBatchUpdateResponse,
)


@router.patch("/interactions/{interaction_id}/facts", response_model=FactsBatchUpdateResponse)
@router.patch("/interactions/{interaction_id}/facts/", response_model=FactsBatchUpdateResponse)
async def patch_v2_tools_interaction_facts_batch(
    interaction_id: str,
    body: FactsBatchUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti §13.5 facts_batch_update — batch update multiple facts.

    Spec: ``PATCH /interactions/{id}/facts/`` (operationId
    ``facts_batch_update``). Path: ``/api/v2/tools/interactions/{interaction_id}/facts/``
    (mounted under the existing ``/api/v2/tools`` prefix).

    Request body: ``{facts: [{factId, text?, group?, isDiscarded?}, ...]}``
    — ``factId`` required, the rest optional.
    Response: ``{facts: [{id, text, group, groupId, source, isDiscarded, createdAt, updatedAt}, ...]}``
    — all 8 fields **required** per spec, per item.

    All fact ids are resolved within the authenticated interaction scope before
    any mutation; valid rows are then updated in request order.

    Error response per spec is **504** (RFC9457 ``ErrorResponse``).
    """
    if len(body.facts) > 100:
        raise HTTPException(status_code=422, detail="facts_count_invalid")
    fact_ids = [item.factId for item in body.facts]
    if len(fact_ids) != len(set(fact_ids)):
        raise HTTPException(status_code=422, detail="duplicate_fact_id")
    scope = _fact_scope(current_user, current_org, interaction_id)
    scoped_rows = await clinical_fact_repository.list(db, **scope)
    rows = {row.fact_id: row for row in scoped_rows if row.fact_id in fact_ids}
    if set(rows) != set(fact_ids):
        raise HTTPException(status_code=404, detail="fact_not_found")
    for fact_in in body.facts:
        if fact_in.text is not None and (
            not fact_in.text.strip() or len(fact_in.text.strip()) > 4000
        ):
            raise HTTPException(status_code=422, detail="fact_text_invalid")
        if fact_in.group is not None and (
            not fact_in.group.strip() or len(fact_in.group.strip()) > 96
        ):
            raise HTTPException(status_code=422, detail="fact_group_invalid")
    out: List[FactsBatchUpdateItem] = []
    for fact_in in body.facts:
        row = await clinical_fact_repository.update(
            db,
            rows[fact_in.factId],
            text=fact_in.text.strip() if fact_in.text is not None else None,
            group_key=fact_in.group.strip() if fact_in.group is not None else None,
            is_discarded=fact_in.isDiscarded,
        )
        projected = _fact_update_response(row)
        out.append(
            FactsBatchUpdateItem(**projected.model_dump())
        )
    return FactsBatchUpdateResponse(facts=out)
