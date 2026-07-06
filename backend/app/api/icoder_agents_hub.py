"""Phase 3-B1 — Corti-style Agent Hub endpoint.

Restored 2026-07-04 (Phase 3-B1 Section B). The Phase 2.1-B deletion of
``icoder_agents_hub.py`` (1029 LOC) left the frontend AgentsPage with no
pack-mastered data source. This router rebuilds the Hub with
``official_agents/**/agent_pack.json`` as the canonical source.

Contract (per Phase 3-B1 prompt §B):

- ``GET /api/icoder/agents/hub`` — Corti-style Hub card list, no auth,
  read-only, pack-mastered.
- hidden_from_hub=true packs do NOT appear.
- metadata-only packs appear with ``runnable=false`` and badge
  ``"Coming Soon"`` (no Run button on the frontend).
- stub packs (``agent_type=expert-stub``) do NOT appear.
- internal_engine packs do NOT appear.
- Medical Coding Agent appears with ``runnable=true``, badge
  ``"MVP / AI-assisted / Human review required"``.
- production_ready=false is always surfaced — never displayed as
  production-ready.
- No run path (empty ``experts[]``) ⇒ ``runnable=false``.

Phase 3-B2 Loop 1 (2026-07-05): Added ``POST /{agent_id}/clone`` endpoint
and ``clone_url``/``chat_url``/``customize_url``/``run_url`` fields to
each Hub card. Cloning copies a prebuilt Agent (organization_id=NULL)
into the requesting user's org as a custom Agent (is_prebuilt=False).
Conflict strategy: idempotent — if a clone already exists for
``(org, source_agent_ref)``, return 200 OK with the existing record's
URLs (no duplicate created). First clone returns 201 Created.

This router does NOT execute agents — it only describes them. Execution
lives in A2A mainline (Section D) and the compatibility shim (Section E).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.agent import Agent
from app.models.user import User
from app.models.organization import Organization

router = APIRouter(prefix="/api/icoder/agents", tags=["agent-hub"])


# ---------------------------------------------------------------------------
# Pack discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_AGENTS_DIR = _REPO_ROOT / "official_agents"


def _load_packs() -> list[dict[str, Any]]:
    """Read every ``agent_pack.json`` under ``official_agents/``."""
    packs: list[dict[str, Any]] = []
    if not OFFICIAL_AGENTS_DIR.exists():
        return packs
    for path in sorted(OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                packs.append(json.load(f))
        except Exception:
            # Skip malformed packs silently — Section A.5 audit catches them
            continue
    return packs


# ---------------------------------------------------------------------------
# Visibility + runnability derivation
# ---------------------------------------------------------------------------

def _is_visible(pack: dict[str, Any]) -> bool:
    """A pack is Hub-visible iff it is NOT hidden_from_hub AND not a
    stub/internal_engine. Metadata-only certified packs ARE visible
    (with Coming Soon badge)."""
    manifest = pack.get("manifest") or {}
    if manifest.get("hidden_from_hub") is True:
        return False
    agent_type = pack.get("agent_type")
    if agent_type in ("expert-stub", "internal_engine"):
        return False
    return True


def _is_runnable(pack: dict[str, Any]) -> bool:
    """A pack is runnable iff it has at least one expert AND its maturity
    is mvp/runnable/production-ready (NOT metadata-only/stub/internal)."""
    experts = pack.get("experts") or []
    if not experts:
        return False
    manifest = pack.get("manifest") or {}
    maturity = manifest.get("maturity")
    if maturity in ("metadata-only", "stub", None):
        return False
    return maturity in ("mvp", "runnable", "production-ready")


def _badge(pack: dict[str, Any], runnable: bool) -> str:
    """Corti-style badge shown on the Hub card."""
    manifest = pack.get("manifest") or {}
    maturity = manifest.get("maturity")
    if runnable:
        # MVP / AI-assisted / Human review required
        human = manifest.get("human_review") or "required"
        return f"MVP / AI-assisted / Human review {human}"
    if maturity == "metadata-only":
        return "Coming Soon / Metadata only"
    return "Coming Soon"


def _workflow_summary(pack: dict[str, Any]) -> str:
    """Human-readable workflow summary. For MedCodER packs, derive from
    pipeline.stages. For others, return a one-line summary."""
    pipeline = pack.get("pipeline")
    if isinstance(pipeline, dict) and pipeline.get("stages"):
        stages = [s.get("name", "?") for s in pipeline.get("stages") if isinstance(s, dict)]
        return f"Pipeline: {' → '.join(stages)}"
    # Medical Coding Agent (Corti 7-step) — hardcoded by agent_ref
    if pack.get("agent_ref") == "icoder/medical-coding-agent@2.0.0":
        return "Corti 7-step: Synthesize → Extract → Search → Assign → Validate → Identify Gaps → Review"
    return pack.get("manifest", {}).get("description", "")


def _agent_id_from_ref(agent_ref: str) -> str:
    """Derive the short agent_id from a full agent_ref.

    ``icoder/medical-coding-agent@2.0.0`` → ``medical-coding-agent``.
    Used in URL paths (clone, chat, A2A) where the slash+@ in agent_ref
    would break routing.
    """
    if not agent_ref:
        return ""
    tail = agent_ref.split("/")[-1]
    return tail.split("@")[0]


def _build_card(pack: dict[str, Any]) -> dict[str, Any]:
    """Project an agent_pack.json into a Corti-style Hub card."""
    manifest = pack.get("manifest") or {}
    runnable = _is_runnable(pack)
    agent_ref = pack.get("agent_ref", "")
    agent_id = _agent_id_from_ref(agent_ref)

    # A2A endpoint — only set for runnable packs that declare one
    a2a = pack.get("a2a") or {}
    a2a_endpoint = a2a.get("endpoint") if runnable else None

    # Run endpoint — the compatibility shim. Only for runnable packs.
    run_endpoint = None
    if runnable:
        run_endpoint = f"/api/runtime-platform/agents/{agent_ref}/run"

    # Phase 3-B2 Loop 1: Corti-style action URLs. clone_url is concrete
    # (POST to clone into the caller's org). chat_url + customize_url are
    # templates — the {project_agent_id} placeholder is replaced by the
    # clone response's concrete value. run_url is the A2A mainline.
    clone_url = f"/api/icoder/agents/{agent_id}/clone" if runnable else None
    chat_url = f"/agents/{{project_agent_id}}/chat" if runnable else None
    customize_url = f"/ai-studio/agents/{{project_agent_id}}" if runnable else None
    run_url = a2a_endpoint if runnable else None

    # Permissions / red lines
    permissions = pack.get("permissions") or {}
    red_lines = {
        "no_upcoding": permissions.get("no_upcoding", False),
        "no_inference": permissions.get("no_inference", False),
        "evidence_required": permissions.get("evidence_required", False),
        "production_writeback_blocked": permissions.get(
            "production_writeback_blocked", False
        ),
    }

    # Requirements
    requirements = pack.get("requirements") or {}
    llm_caps = pack.get("llm_capabilities") or {}
    required_models = [
        m.get("name") for m in (llm_caps.get("required_models") or [])
        if isinstance(m, dict) and m.get("name")
    ]

    # Output contract
    output_contract = pack.get("output_contract") or {}
    output_summary = {
        "schema_ref": output_contract.get("schema_ref"),
        "required_fields": output_contract.get("required_fields") or [],
    }

    # Non-goals / constraints
    non_goals = pack.get("non_goals") or []
    human_review_when = pack.get("human_review_required_when") or []

    return {
        "agent_ref": agent_ref,
        "agent_id": agent_id,
        "name": manifest.get("name", ""),
        "display_name": manifest.get("name", ""),
        "category": manifest.get("category", ""),
        "category_display": manifest.get("category_display", ""),
        # Phase 3-B2 Loop 4: top-level use_case (manifest.use_case with
        # fallback to category for pre-Loop 4 packs). Used by /hub?use_case=
        # filter and the frontend use_case dropdown.
        "use_case": manifest.get("use_case") or manifest.get("category", ""),
        "icon": manifest.get("icon", ""),
        "version": manifest.get("version", pack.get("agent_ref", "").split("@")[-1]),
        "description": manifest.get("description", ""),
        "maturity": manifest.get("maturity", ""),
        "production_ready": manifest.get("production_ready", False),
        "human_review": manifest.get("human_review", "required"),
        "hidden_from_hub": manifest.get("hidden_from_hub", False),
        "runnable": runnable,
        "badge": _badge(pack, runnable),
        "tags": manifest.get("tags", []),
        "workflow": _workflow_summary(pack),
        "red_lines": red_lines,
        "requirements": {
            "min_runtime_version": requirements.get("min_runtime_version"),
            "icoder_runtime_modules": requirements.get("icoder_runtime_modules") or [],
            "required_models": required_models,
        },
        "output_contract": output_summary,
        "non_goals": non_goals,
        "human_review_required_when": human_review_when,
        "a2a_endpoint": a2a_endpoint,
        "run_endpoint": run_endpoint,
        # Phase 3-B2 Loop 1: Corti-style action URLs.
        "clone_url": clone_url,
        "chat_url": chat_url,
        "customize_url": customize_url,
        "run_url": run_url,
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/hub", operation_id="icoder_agents_hub_list_v1")
async def list_hub_agents(
    use_case: str | None = Query(
        None,
        description="Filter by manifest.use_case (Phase 3-B2 Loop 4).",
    ),
) -> dict[str, Any]:
    """Corti-style Agent Hub card list.

    Reads ``official_agents/**/agent_pack.json`` as the canonical source.
    Filters:

    - ``hidden_from_hub=true`` packs excluded.
    - ``agent_type=expert-stub`` packs excluded.
    - ``agent_type=internal_engine`` packs excluded.
    - ``use_case`` query param filters by ``manifest.use_case`` (Phase 3-B2 Loop 4).

    Metadata-only certified packs ARE included with ``runnable=false`` and
    ``badge="Coming Soon / Metadata only"``. Medical Coding Agent appears
    with ``runnable=true`` and ``badge="MVP / AI-assisted / Human review required"``.

    No auth — this is a product browsing endpoint. Execution is gated
    separately at the run endpoint.
    """
    packs = _load_packs()
    cards = [_build_card(p) for p in packs if _is_visible(p)]
    if use_case:
        cards = [c for c in cards if _card_use_case(c) == use_case]
    # Sort: runnable first, then by category, then by name
    cards.sort(key=lambda c: (not c["runnable"], c["category"], c["name"]))
    return {
        "agents": cards,
        "total": len(cards),
        "source": "official_agents/agent_pack.json",
        "schema_version": "1.1",
    }


def _card_use_case(card: dict[str, Any]) -> str:
    """Extract use_case from a Hub card (Phase 3-B2 Loop 4 filter).

    Order of precedence:
      1. Top-level ``use_case`` field (set by _build_card from
         ``manifest.use_case``).
      2. Fallback to ``category`` for backward compat (pre-Loop 4 packs
         that haven't yet declared use_case in their manifest).
    """
    return str(card.get("use_case") or card.get("category") or "")


# ---------------------------------------------------------------------------
# Phase 3-B2 Loop 1 — Clone endpoint (Gap 2.3)
# ---------------------------------------------------------------------------


class CloneRequest(BaseModel):
    """Request body for POST /api/icoder/agents/{agent_id}/clone.

    All fields optional — the caller can simply POST {} to clone with
    defaults. ``project_id`` is accepted for Corti API parity but maps
    to the caller's organization (iCoDer is org-scoped, not project-scoped).
    """
    project_id: str | None = Field(
        None, description="Corti-style project_id. Maps to org_id in iCoDer."
    )
    name: str | None = Field(None, description="Override the cloned agent's name.")
    description: str | None = Field(None, description="Override description.")
    open_after_clone: bool = Field(
        True, description="If true, response includes ready-to-navigate URLs."
    )


class CloneResponse(BaseModel):
    """Response body for POST /api/icoder/agents/{agent_id}/clone."""
    project_agent_id: str = Field(..., description="DB UUID of the cloned Agent.")
    runtime_agent_id: str = Field(
        ..., description="Short agent_id used in A2A paths (e.g. 'medical-coding-agent')."
    )
    source_agent_ref: str = Field(
        ..., description="Original agent_ref (e.g. 'icoder/medical-coding-agent@2.0.0')."
    )
    chat_url: str
    customize_url: str
    run_url: str
    cloned: bool = Field(
        ..., description="True if a new clone was created; False if existing clone returned (idempotent)."
    )


async def _find_prebuilt_by_agent_id(db: AsyncSession, agent_id: str) -> Agent | None:
    """Look up a prebuilt Agent by short agent_id (derived from config.agent_ref)."""
    q = select(Agent).where(Agent.is_prebuilt == True)  # noqa: E712
    result = await db.execute(q)
    for agent in result.scalars().all():
        cfg = agent.config or {}
        ref = cfg.get("agent_ref", "") if isinstance(cfg, dict) else ""
        if _agent_id_from_ref(ref) == agent_id:
            return agent
    return None


async def _find_existing_clone(
    db: AsyncSession, org_id: str, source_agent_ref: str
) -> Agent | None:
    """Look up an existing clone for (org, source_agent_ref)."""
    q = select(Agent).where(
        Agent.is_prebuilt == False,  # noqa: E712
        Agent.organization_id == org_id,
    )
    result = await db.execute(q)
    for agent in result.scalars().all():
        cfg = agent.config or {}
        if not isinstance(cfg, dict):
            continue
        if cfg.get("source_agent_ref") == source_agent_ref:
            return agent
    return None


@router.post(
    "/{agent_id}/clone",
    operation_id="icoder_agents_clone_v1",
)
async def clone_agent(
    agent_id: str,
    response: Response,
    body: CloneRequest | None = None,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clone a prebuilt Agent into the caller's organization.

    Phase 3-B2 Loop 1 (Gap 2.3). The source Agent is identified by
    ``agent_id`` (short form, e.g. ``medical-coding-agent``). The clone
    creates a new ``Agent`` row with ``is_prebuilt=False``,
    ``organization_id=<caller's org>``, ``status=published``, and
    ``config.source_agent_ref=<original agent_ref>``.

    Conflict strategy (idempotent): if a clone already exists for
    ``(org, source_agent_ref)``, return **200 OK** with the existing
    record's URLs (no duplicate created). First clone returns 201 Created.

    Errors:
    - 404: agent_id not found among prebuilt agents.
    - 403: auth failure (no valid token).
    - 400: malformed request body.
    """
    body = body or CloneRequest()

    # 1. Look up the source prebuilt Agent.
    source = await _find_prebuilt_by_agent_id(db, agent_id)
    if not source:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "message": f"No prebuilt agent with agent_id='{agent_id}'",
                "agent_id": agent_id,
            },
        )
    source_agent_ref = (source.config or {}).get("agent_ref", "")

    # 2. Check for existing clone (idempotent).
    existing = await _find_existing_clone(db, org.id, source_agent_ref)
    if existing:
        # Idempotent: 200 OK with existing record's URLs (no duplicate).
        response.status_code = 200
        return {
            "project_agent_id": existing.id,
            "runtime_agent_id": agent_id,
            "source_agent_ref": source_agent_ref,
            "chat_url": f"/agents/{existing.id}/chat",
            "customize_url": f"/ai-studio/agents/{existing.id}",
            "run_url": f"/api/icoder/agents/{agent_id}/v1/message:send",
            "cloned": False,
        }

    # 3. Create the clone.
    cloned = Agent(
        organization_id=org.id,
        name=body.name or f"{source.name} (Clone)",
        description=body.description or source.description,
        system_prompt=source.system_prompt,
        icon=source.icon,
        category=source.category,
        expert_ids=source.expert_ids or [],
        default_expert_id=source.default_expert_id or "",
        a2a_enabled=source.a2a_enabled,
        config={
            **(source.config or {}),
            "source_agent_ref": source_agent_ref,
            "cloned_from_prebuilt": True,
            "cloned_by": user.id,
            "clone_project_id": body.project_id,
        },
        is_prebuilt=False,
        is_published=True,
        status="published",
        version=source.version or "1.0.0",
        created_by=user.id,
        usage_count=0,
    )
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)

    # First clone: 201 Created.
    response.status_code = 201
    return {
        "project_agent_id": cloned.id,
        "runtime_agent_id": agent_id,
        "source_agent_ref": source_agent_ref,
        "chat_url": f"/agents/{cloned.id}/chat",
        "customize_url": f"/ai-studio/agents/{cloned.id}",
        "run_url": f"/api/icoder/agents/{agent_id}/v1/message:send",
        "cloned": True,
    }
