"""Agent Card + Quick-Create API — A1B-AE.4.

Two new Corti-compatible surfaces:

- ``POST /api/v1/agents/quick`` — Corti Console create-then-customize
  UX. Accepts name-only, returns an ID for subsequent customization
  via PUT /api/v1/agents/{id} (existing agents.py router).

- ``GET  /api/v1/agents/{id}/card`` — Corti public §6 Agent Card.
  READ-ONLY projection for A2A discovery. Inline-expands expert_ids[]
  to full Expert records (with MCP servers) so consumers get a
  single-round-trip view of the Agent's capabilities.

- ``GET  /api/v1/agents/resolve/{key}`` — alias-aware lookup.
  Resolves legacy underscore-form keys to canonical dash-form before
  hitting the DB. This is the application-layer half of the clone-404
  fix (data-layer half is Migration 023's backfill of canonical_key
  + aliases on the 3 known dual-named Packs).

These endpoints sit alongside the existing /api/rest/v1/agent_definitions
router (Phase 2.1-C) — they do NOT replace it. The existing router
remains the primary management surface; this module adds the
Corti-compatible discovery + quick-create surfaces only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.agent import Agent, AGENT_TYPE_DEFAULT
from app.models.expert import Expert, McpServer
from app.models.user import User
from app.models.organization import Organization
from app.schemas.agent_card import (
    AgentCard,
    AgentCardExpert,
    AgentCardMcpServer,
    AgentQuickCreate,
    AgentQuickCreateResponse,
)
from app.services.alias_resolver import alias_resolver


router = APIRouter(prefix="/api/v1/agents", tags=["agent-card-a1b-ae-4"])


# ── Helpers ─────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Same slug algorithm as Migration 023 — keep in sync."""
    import hashlib
    import re
    if not name:
        return ""
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").lower()
    if not s:
        s = "agent-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return s


async def _build_expert_card_entries(
    db: AsyncSession,
    expert_ids: list[str],
    org_id: str,
) -> list[AgentCardExpert]:
    """Inline-expand expert_ids into AgentCardExpert objects.

    Unknown expert_ids are silently dropped from the Card — the Card
    is a READ-ONLY discovery projection, not a write path.
    """
    if not expert_ids:
        return []
    stmt = select(Expert).where(
        Expert.id.in_(expert_ids),
    )
    result = await db.execute(stmt)
    rows = {r.id: r for r in result.scalars().all()}

    # Also try by canonical_key in case the IDs are actually keys
    missing = [eid for eid in expert_ids if eid not in rows]
    if missing:
        stmt2 = select(Expert).where(Expert.canonical_key.in_(missing))
        result2 = await db.execute(stmt2)
        for r in result2.scalars().all():
            if r.canonical_key and r.canonical_key in missing:
                rows[r.canonical_key] = r

    # Preserve the order of expert_ids in the output
    out: list[AgentCardExpert] = []
    for eid in expert_ids:
        row = rows.get(eid)
        if row is None:
            # Try canonical-key lookup as final fallback
            row = rows.get(alias_resolver.resolve_expert_key(eid))
        if row is None:
            continue
        # Load MCP servers for this Expert
        mcp_stmt = select(McpServer).where(McpServer.expert_id == row.id)
        mcp_rows = (await db.execute(mcp_stmt)).scalars().all()
        mcp_servers = [
            AgentCardMcpServer(
                id=m.id,
                name=m.name,
                transportType=m.transport_type or "streamable_http",
                authorizationType=m.authorization_type or m.auth_type or "none",
                url=m.url,
            )
            for m in mcp_rows
        ]
        out.append(
            AgentCardExpert(
                id=row.id,
                name=row.name,
                canonical_key=row.canonical_key,
                origin=row.origin or "ICODER_INTERNAL",
                corti_alignment=row.corti_alignment or "UNKNOWN",
                mcpServers=mcp_servers,
            )
        )
    return out


def _agent_to_card(
    agent: Agent,
    experts: list[AgentCardExpert],
) -> AgentCard:
    return AgentCard(
        id=agent.id,
        name=agent.name,
        description=agent.description or "",
        systemPrompt=agent.system_prompt or "",
        agentType=agent.agent_type or AGENT_TYPE_DEFAULT,
        experts=experts,
        mcpServers=[],  # Agent-level MCP servers are not yet modelled; Experts carry them
        canonical_key=agent.canonical_key,
        aliases=agent.aliases or [],
        version=agent.version or "1.0.0",
        status=agent.status or "draft",
        organization_id=agent.organization_id,
        created_at=getattr(agent, "created_at", None),
        updated_at=getattr(agent, "updated_at", None),
    )


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/quick", response_model=AgentQuickCreateResponse)
async def quick_create_agent(
    body: AgentQuickCreate,
    from_preset: str | None = None,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti Console create-then-customize UX — name-only first step.

    Creates a draft Agent with the given name and returns its ID.
    Caller is expected to follow up with PUT /api/v1/agents/{id} to
    set description, systemPrompt, expert_ids, etc.

    A1B-AE-R.2 (2026-07-23): optional ``from_preset`` query parameter
    pre-populates the Agent from a Preset Agent Card in
    ``icoder_preset_agents.json``. When ``from_preset`` is set:

    - ``name`` defaults to the preset's name_zh if body.name is empty
    - ``description``, ``system_prompt``, ``agent_type``, ``canonical_key``,
      and the preset's expert keys are copied onto the new Agent
    - ``delegates_to_pack`` from the preset is stored in config for the
      runtime to resolve

    Provenance: ICODER_INTERNAL (matches Corti Console observed
    behaviour but does not copy any Corti-private material).
    """
    # A1B-AE-R.2 — preset materialization path
    preset = None
    if from_preset:
        from app.services.preset_agents import get_preset
        preset = get_preset(from_preset)
        if preset is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Preset not found for from_preset={from_preset!r}"
                ),
            )

    name = (body.name or "").strip()
    if not name:
        if preset is not None:
            name = preset.name
        else:
            raise HTTPException(status_code=422, detail="name must not be empty")

    canonical = _slugify(name)
    description = ""
    system_prompt = ""
    agent_type = AGENT_TYPE_DEFAULT
    expert_ids: list[str] = []
    config: dict = {}
    if preset is not None:
        description = preset.description
        system_prompt = preset.system_prompt
        agent_type = preset.agent_type or AGENT_TYPE_DEFAULT
        expert_ids = [e.canonical_key for e in preset.experts]
        canonical = preset.canonical_key
        config = {
            "delegates_to_pack": preset.delegates_to_pack,
            "corti_alignment": preset.corti_alignment,
            "default_runtime_mode": preset.default_runtime_mode,
            "available_runtime_modes": list(preset.available_runtime_modes),
            "red_lines": dict(preset.red_lines),
            "source_preset": preset.canonical_key,
        }

    agent = Agent(
        organization_id=org.id,
        name=name,
        description=description,
        system_prompt=system_prompt,
        icon="Bot",
        category="general",
        expert_ids=expert_ids,
        default_expert_id=expert_ids[0] if expert_ids else "",
        a2a_enabled=False,
        config=config,
        version="1.0.0",
        status="draft",
        is_prebuilt=False,
        is_published=False,
        created_by=user.id,
        usage_count=0,
        canonical_key=canonical,
        agent_type=agent_type,
        aliases=[],
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return AgentQuickCreateResponse(
        id=agent.id,
        name=agent.name,
        canonical_key=agent.canonical_key,
        agent_type=agent.agent_type,
        status=agent.status,
        version=agent.version,
        next_step="customize",
    )


@router.get("/resolve/{key}")
async def resolve_agent_by_key(
    key: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Alias-aware Agent lookup by canonical_key OR alias.

    Returns 200 with the Agent body on hit, 404 on miss. The lookup
    order is:

    1. DB row where canonical_key == key (after alias resolution)
    2. DB row where canonical_key == alias_resolver(key)
    3. DB row where key appears in aliases JSON (legacy form)

    This endpoint is the application-layer half of the clone-404 fix.
    """
    resolved = alias_resolver.resolve_agent_key(key)

    # Try direct canonical_key match first
    stmt = select(Agent).where(
        Agent.organization_id == org.id,
        Agent.canonical_key == resolved,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()

    # Fallback: try raw key in case the resolver didn't know it
    if agent is None and resolved != key:
        stmt2 = select(Agent).where(
            Agent.organization_id == org.id,
            Agent.canonical_key == key,
        )
        agent = (await db.execute(stmt2)).scalar_one_or_none()

    # Fallback: scan aliases JSON
    if agent is None:
        stmt3 = select(Agent).where(Agent.organization_id == org.id)
        rows = (await db.execute(stmt3)).scalars().all()
        for r in rows:
            if key in (r.aliases or []):
                agent = r
                break

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent not found for key={key!r} (resolved={resolved!r})",
        )

    return {
        "id": agent.id,
        "name": agent.name,
        "canonical_key": agent.canonical_key,
        "aliases": agent.aliases or [],
        "agent_type": agent.agent_type,
        "status": agent.status,
        "version": agent.version,
        "requested_key": key,
        "resolved_key": resolved,
    }


@router.get("/{agent_id}/card", response_model=AgentCard)
async def get_agent_card(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Corti public §6 Agent Card — A2A discovery projection.

    Inline-experts expert_ids[] to full Expert records with their MCP
    servers so consumers get a single-round-trip view of the Agent's
    capabilities.
    """
    stmt = select(Agent).where(
        Agent.id == agent_id,
        Agent.organization_id == org.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    experts = await _build_expert_card_entries(db, agent.expert_ids or [], org.id)
    return _agent_to_card(agent, experts)
