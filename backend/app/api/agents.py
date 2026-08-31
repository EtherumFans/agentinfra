# Phase 2.1-C (2026-07-04) — Migrated from /api/agents to /rest/v1/agent_definitions (Corti 风格).
"""Agent CRUD API — manage Agents as first-class backend entities.

iCoDer Agentic Framework equivalent: "Agent is a backend entity that composes
multiple Experts. Users create/configure Agents, which then orchestrate
Experts to complete tasks."

Corti-style REST path: /api/rest/v1/agent_definitions/* (Phase 2.1-C migrated
from legacy /api/agents/* prefix; the /api namespace is kept per iCoDer
convention, matching /api/v2/tools/* — Corti's actual path is /rest/v1/
agent_definitions, but iCoDer namespaces all client-facing routers under
/api). The 9 management endpoints (list/get/create/update/delete/
categories/templates/version/clone) are exposed on this prefix; A2A
discovery (list+card) remains on /api/icoder/agents via the lifespan-
mounted A2A routes.
"""
import json
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.middleware.audit import log_action
from app.models.user import User
from app.models.agent import Agent
from app.models.expert import Expert
from app.models.organization import Organization
# Phase 2.1-A (2026-07-02): legacy agent_runner stub removed.
# The `_LegacyAgentRunnerStub` symbol (Phase 2-B) is gone — any caller that
# still hits the legacy `agent_runner.run/stream` path now gets a clear 410
# Gone redirect to the A2A mainline. The new execution path lives in
# `app.icoder.agent_runtime.orchestrator.InboundHandler` (mounted via
# `mount_a2a` in app/main.py).
from app.services.agent_analytics import agent_analytics

router = APIRouter(prefix="/api/rest/v1/agent_definitions", tags=["agent-definitions"])


# ---- Schemas ----

class AgentExpertBinding(BaseModel):
    expert_id: str
    expert_name: str = ""

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    system_prompt: str = ""
    icon: str = "Bot"
    category: str = "general"
    expert_ids: list[str] = []
    default_expert_id: str = ""
    a2a_enabled: bool = False
    config: dict | None = None

class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    icon: str | None = None
    category: str | None = None
    expert_ids: list[str] | None = None
    default_expert_id: str | None = None
    a2a_enabled: bool | None = None
    config: dict | None = None
    status: str | None = None
    is_published: bool | None = None
    version: str | None = None


_AGENT_LIFECYCLE_STATUSES = frozenset({"draft", "published", "archived"})


def _bump_patch_version(value: str | None) -> str:
    """Return a strict three-part semantic patch version."""

    raw = str(value or "1.0.0").strip()
    parts = raw.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "agent_version_invalid",
                "version": raw,
                "message": "Agent version must use numeric MAJOR.MINOR.PATCH.",
            },
        )
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def _lifecycle_projection(agent: Agent) -> dict:
    status = str(agent.status or "draft").lower()
    if status not in _AGENT_LIFECYCLE_STATUSES:
        status = "draft"
    effective_published = status == "published" and bool(agent.is_published)
    if agent.is_prebuilt:
        allowed_actions: list[str] = []
    elif status == "draft":
        allowed_actions = ["publish", "delete"]
    elif status == "published":
        allowed_actions = ["archive", "version", "delete"]
    else:
        allowed_actions = ["restore", "delete"]
    return {
        "state": status,
        "effective_published": effective_published,
        "run_action_enabled": effective_published,
        "allowed_actions": allowed_actions,
        "version": agent.version or "1.0.0",
    }


async def _audit_agent_lifecycle(
    db: AsyncSession,
    *,
    agent: Agent,
    org: Organization,
    user: User,
    action: str,
    details: dict | None = None,
) -> None:
    await log_action(
        db,
        user_id=user.id,
        username=getattr(user, "username", None),
        action=action,
        resource_type="agent",
        resource_id=agent.id,
        details=details or {},
        organization_id=org.id,
    )


_CLONE_PROTECTED_CONFIG_FIELDS = frozenset({
    "agent_ref",
    "runtime_agent_id",
    "agent_type",
    "format_version",
    "use_case",
    "maturity",
    "human_review",
    "production_ready",
    "hidden_from_hub",
    "non_goals",
    "output_contract",
    "permissions",
    "requirements",
    "llm_capabilities",
    "a2a",
    "runtime_binding",
    "source_agent_ref",
    "cloned_from_prebuilt",
    "cloned_by",
    "clone_project_id",
})


def _is_prebuilt_clone_config(config: object) -> bool:
    return bool(
        isinstance(config, dict)
        and config.get("cloned_from_prebuilt") is True
        and str(config.get("source_agent_ref") or "").strip()
    )


def _protect_clone_runtime_config(agent: Agent, body: AgentUpdate) -> AgentUpdate:
    """Keep source-owned runtime fields immutable on a project clone.

    The public update API may carry a full config object from the editor. It is
    safe to merge mutable project keys, but changing provenance, contracts,
    permissions or integrity bindings would let a tenant forge a runtime Pack.
    """

    current = agent.config or {}
    if not _is_prebuilt_clone_config(current):
        return body

    if body.config is None:
        return body
    incoming = dict(body.config)
    changed = sorted(
        key
        for key in _CLONE_PROTECTED_CONFIG_FIELDS
        if key in incoming and incoming.get(key) != current.get(key)
    )
    if changed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "clone_runtime_field_immutable",
                "fields": changed,
                "message": "Source-owned clone runtime fields cannot be changed.",
            },
        )
    return body.model_copy(update={"config": {**current, **incoming}})


def _protect_dedicated_clone_expert_graph(
    agent: Agent,
    body: AgentUpdate,
) -> None:
    """Reject a saved configuration that misrepresents a fixed source graph."""

    if body.expert_ids is None or body.expert_ids:
        return
    current = agent.config or {}
    if not _is_prebuilt_clone_config(current):
        return

    from app.services.agent_runtime_pack import load_governed_source_pack

    source_pack = load_governed_source_pack(
        str(current.get("source_agent_ref") or "")
    )
    source_expert_ids = [
        str(item.get("expert_id") or item.get("id") or "").strip()
        for item in (source_pack.get("experts") or [])
        if isinstance(item, dict)
        and str(item.get("expert_id") or item.get("id") or "").strip()
    ]
    dedicated_runtime = not str(
        source_pack.get("backend_provider") or ""
    ).strip()
    if dedicated_runtime and source_expert_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "clone_dedicated_expert_removal_unsupported",
                "source_expert_ids": source_expert_ids,
                "message": (
                    "This dedicated runtime keeps its governed source Expert "
                    "graph. Bind project Experts as additive specialization "
                    "or restore the source Expert bindings."
                ),
            },
        )


async def _validate_expert_bindings(
    db: AsyncSession,
    *,
    organization_id: str,
    expert_ids: list[str],
    default_expert_id: str = "",
) -> None:
    """Reject unknown or cross-tenant Expert references before persistence."""

    unique_ids = list(dict.fromkeys(expert_ids))
    if default_expert_id and default_expert_id not in unique_ids:
        raise HTTPException(
            status_code=422,
            detail={"error": "default_expert_not_bound"},
        )
    if not unique_ids:
        return
    visible_ids = set(
        (
            await db.execute(
                select(Expert.id).where(
                    Expert.id.in_(unique_ids),
                    Expert.organization_id == organization_id,
                    Expert.is_published.is_(True),
                )
            )
        ).scalars().all()
    )
    if visible_ids != set(unique_ids):
        raise HTTPException(
            status_code=422,
            detail={"error": "expert_binding_unavailable"},
        )


def _runtime_customization_contract(agent: Agent) -> dict | None:
    """Describe clone customization semantics without exposing policy text."""

    config = agent.config or {}
    if not _is_prebuilt_clone_config(config):
        return None
    from app.services.agent_runtime_pack import (
        CloneRuntimeConfigurationError,
        load_governed_source_pack,
    )

    source_ref = str(config.get("source_agent_ref") or "")
    try:
        source_pack = load_governed_source_pack(source_ref)
    except CloneRuntimeConfigurationError as exc:
        return {
            "is_clone": True,
            "source_agent_ref": source_ref,
            "source_status": "unavailable",
            "source_error": exc.code,
        }
    source_expert_ids = [
        str(item.get("expert_id") or item.get("id") or "").strip()
        for item in (source_pack.get("experts") or [])
        if isinstance(item, dict)
        and str(item.get("expert_id") or item.get("id") or "").strip()
    ]
    configured_ids = [str(value) for value in (agent.expert_ids or [])]
    dedicated = not str(source_pack.get("backend_provider") or "").strip()
    return {
        "is_clone": True,
        "source_agent_ref": source_ref,
        "source_status": "available",
        "runtime_kind": "dedicated" if dedicated else "provider",
        "system_prompt_mode": (
            "additive_specialization" if dedicated else "project_override"
        ),
        "expert_binding_mode": (
            "additive_policy" if dedicated else "project_override"
        ),
        "source_experts_fixed": dedicated,
        "source_expert_ids": source_expert_ids,
        "project_expert_ids": (
            configured_ids
            if dedicated and configured_ids != source_expert_ids
            else [] if dedicated else configured_ids
        ),
    }


async def _agent_to_dict(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "icon": agent.icon,
        "category": agent.category,
        "expert_ids": agent.expert_ids or [],
        "default_expert_id": agent.default_expert_id or "",
        "a2a_enabled": agent.a2a_enabled,
        "config": agent.config or {},
        "runtime_customization": _runtime_customization_contract(agent),
        "is_prebuilt": agent.is_prebuilt,
        "is_published": agent.is_published,
        "version": agent.version or "1.0.0",
        "status": agent.status or "draft",
        "lifecycle": _lifecycle_projection(agent),
        "created_by": agent.created_by,
        "usage_count": agent.usage_count or 0,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


# ---- Endpoints ----

@router.get("")
async def list_agents(
    category: str = "",
    search: str = "",
    type: str = Query("all", enum=["all", "prebuilt", "custom"]),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List agents with optional filter/search."""
    q = select(Agent).where(Agent.organization_id == org.id)
    if type == "prebuilt":
        q = q.where(Agent.is_prebuilt == True)
    elif type == "custom":
        q = q.where(Agent.is_prebuilt == False)
    if category:
        q = q.where(Agent.category == category)
    if search:
        q = q.where(or_(
            Agent.name.ilike(f"%{search}%"),
            Agent.description.ilike(f"%{search}%"),
        ))
    q = q.order_by(Agent.is_prebuilt.desc(), Agent.usage_count.desc())
    result = await db.execute(q)
    agents = result.scalars().all()
    return {"agents": [await _agent_to_dict(a) for a in agents], "total": len(agents)}


@router.post("")
async def create_agent(
    body: AgentCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom agent."""
    await _validate_expert_bindings(
        db,
        organization_id=org.id,
        expert_ids=body.expert_ids,
        default_expert_id=body.default_expert_id or (
            body.expert_ids[0] if body.expert_ids else ""
        ),
    )
    agent = Agent(
        organization_id=org.id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        icon=body.icon,
        category=body.category,
        expert_ids=body.expert_ids,
        default_expert_id=body.default_expert_id or (body.expert_ids[0] if body.expert_ids else ""),
        a2a_enabled=body.a2a_enabled,
        config=body.config or {},
        is_prebuilt=False,
        is_published=True,
        status="published",
        version="1.0.0",
        created_by=user.id,
    )
    db.add(agent)
    await db.flush()
    await _audit_agent_lifecycle(
        db,
        agent=agent,
        org=org,
        user=user,
        action="agent.lifecycle.created_published",
        details={"status": "published", "version": "1.0.0"},
    )
    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


class AgentCloneRequest(BaseModel):
    name: str | None = None
    description: str | None = None

@router.post("/{agent_id}/clone")
async def clone_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    body: AgentCloneRequest | None = None,
):
    """Clone a prebuilt agent or template into a user-owned custom agent.

    A1B-AE.4: agent_id is now alias-aware. Legacy underscore-form
    keys (e.g. ``code_validation``) are resolved to canonical dash-form
    (``code-validation``) before lookup. This closes the clone-404
    root cause identified in A1B-AE.2 §9.
    """
    name_override = body.name if body else None
    description_override = body.description if body else None

    # A1B-AE.4 — alias-aware lookup. The resolver is a no-op if the
    # input is already canonical, so this is safe to call unconditionally.
    from app.services.alias_resolver import alias_resolver
    resolved_id = alias_resolver.resolve_agent_key(agent_id)

    # 1. Try cloning from a DB Agent (prebuilt or custom)
    result = await db.execute(
        select(Agent).where(
            (Agent.id == agent_id) | (Agent.id == resolved_id),
            Agent.organization_id == org.id,
        )
    )
    source = result.scalar_one_or_none()

    # Fallback: try by canonical_key if the ID lookup missed
    if source is None and resolved_id != agent_id:
        result = await db.execute(
            select(Agent).where(Agent.canonical_key == resolved_id)
            .where(Agent.organization_id == org.id)
        )
        source = result.scalar_one_or_none()
    if source:
        cloned = Agent(
            organization_id=org.id,
            name=name_override or f"{source.name} (Copy)",
            description=description_override or source.description,
            system_prompt=source.system_prompt,
            icon=source.icon,
            category=source.category,
            expert_ids=source.expert_ids or [],
            default_expert_id=source.default_expert_id or "",
            a2a_enabled=source.a2a_enabled,
            config=source.config or {},
            is_prebuilt=False,
            is_published=False,
            created_by=user.id,
            status="draft",
            version="1.0.0",
            usage_count=0,
        )
        db.add(cloned)
        await db.flush()
        await _audit_agent_lifecycle(
            db,
            agent=cloned,
            org=org,
            user=user,
            action="agent.lifecycle.cloned_draft",
            details={"status": "draft", "version": "1.0.0"},
        )
        await db.commit()
        await db.refresh(cloned)
        return await _agent_to_dict(cloned)

    # 2. Try cloning from a catalog template. Governed templates are Pack-
    # mastered and must use the Hub clone endpoint so provenance, permissions,
    # output contract and runtime binding cannot be dropped by this legacy
    # generic clone path.
    template = next(
        (t for t in get_agent_template_catalog() if t["id"] == agent_id),
        None,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Agent or template not found")
    if template.get("template_kind") == "governed_prebuilt":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "governed_template_clone_endpoint_required",
                "agent_id": agent_id,
                "clone_url": template.get("clone_url"),
                "message": (
                    "Governed prebuilt templates must be cloned through the "
                    "Agent Hub endpoint to preserve source runtime policy."
                ),
            },
        )

    cloned = Agent(
        organization_id=org.id,
        name=name_override or f"{template['title']} (Copy)",
        description=description_override or template["description"],
        system_prompt=template["system_prompt"],
        icon=template["icon"],
        category=template["category"],
        expert_ids=template.get("expert_ids", []),
        default_expert_id=template.get("expert_ids", [""])[0] if template.get("expert_ids") else "",
        a2a_enabled=False,
        config=template.get("config", {}),
        is_prebuilt=False,
        is_published=False,
        created_by=user.id,
        status="draft",
        version="1.0.0",
        usage_count=0,
    )
    db.add(cloned)
    await db.flush()
    await _audit_agent_lifecycle(
        db,
        agent=cloned,
        org=org,
        user=user,
        action="agent.lifecycle.created_draft",
        details={"status": "draft", "version": "1.0.0"},
    )
    await db.commit()
    await db.refresh(cloned)
    return await _agent_to_dict(cloned)


@router.get("/categories")
async def agent_categories(db: AsyncSession = Depends(get_db)):
    """List distinct agent categories."""
    from sqlalchemy import func
    result = await db.execute(
        select(Agent.category, func.count(Agent.id)).group_by(Agent.category)
    )
    rows = result.all()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/templates")
async def get_agent_templates():
    """Return the current Pack-mastered Agent template catalog.

    Every governed template is projected from the same visible launch-
    candidate Pack boundary as Agent Hub. Only the two explicitly generic
    blank templates remain locally defined.
    """
    return {"templates": get_agent_template_catalog()}


@router.get("/templates/{template_id}/download")
async def download_template_pack(template_id: str):
    """Download a template as a .icoder-agent package file."""
    from fastapi.responses import Response
    from icoder_runtime.agent_pack import pack_from_template

    template = next(
        (t for t in get_agent_template_catalog() if t["id"] == template_id),
        None,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.get("template_kind") == "governed_prebuilt":
        pack = _visible_pack_for_template_id(template_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Template not found")
        # Hub discovery adds private projection metadata such as file mtime.
        # A downloaded Pack must contain only the canonical persisted fields.
        pack = {key: value for key, value in pack.items() if not key.startswith("_")}
        version = str((pack.get("manifest") or {}).get("version") or "1.0.0")
    else:
        pack = pack_from_template(template)
        version = "1.0.0"
    import json
    content = json.dumps(pack, ensure_ascii=False, indent=2)

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{template_id}-v{version}.icoder-agent"',
        },
    )


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get agent detail."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _agent_to_dict(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if (
        body.status is not None
        or body.is_published is not None
        or body.version is not None
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "agent_lifecycle_endpoint_required",
                "fields": [
                    field
                    for field in ("status", "is_published", "version")
                    if getattr(body, field) is not None
                ],
            },
        )
    if str(agent.status or "draft") == "archived":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "archived_agent_immutable",
                "message": "Restore the Agent before editing it.",
            },
        )

    body = _protect_clone_runtime_config(agent, body)
    _protect_dedicated_clone_expert_graph(agent, body)

    next_expert_ids = (
        body.expert_ids if body.expert_ids is not None else (agent.expert_ids or [])
    )
    next_default_expert_id = (
        body.default_expert_id
        if body.default_expert_id is not None
        else (agent.default_expert_id or "")
    )
    if body.expert_ids is not None and body.default_expert_id is None:
        next_default_expert_id = (
            next_default_expert_id
            if next_default_expert_id in next_expert_ids
            else (next_expert_ids[0] if next_expert_ids else "")
        )
        body = body.model_copy(
            update={"default_expert_id": next_default_expert_id},
        )
    if body.expert_ids is not None or body.default_expert_id is not None:
        await _validate_expert_bindings(
            db,
            organization_id=org.id,
            expert_ids=next_expert_ids,
            default_expert_id=next_default_expert_id,
        )

    changed_fields: list[str] = []
    for field in ["name", "description", "system_prompt", "icon", "category",
                   "expert_ids", "default_expert_id", "a2a_enabled", "config"]:
        val = getattr(body, field, None)
        if val is not None and getattr(agent, field) != val:
            setattr(agent, field, val)
            changed_fields.append(field)

    previous_version = agent.version or "1.0.0"
    if changed_fields and str(agent.status or "draft") == "published":
        agent.version = _bump_patch_version(previous_version)
    agent.is_published = str(agent.status or "draft") == "published"

    if changed_fields:
        await _audit_agent_lifecycle(
            db,
            agent=agent,
            org=org,
            user=user,
            action="agent.lifecycle.updated",
            details={
                "changed_fields": sorted(changed_fields),
                "status": agent.status or "draft",
                "previous_version": previous_version,
                "version": agent.version or "1.0.0",
            },
        )

    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


@router.get("/{agent_id}/share")
async def get_agent_share_link(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Generate a shareable link for an agent."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    link = f"/ai-studio/agents/{agent.id}"
    return {"share_url": link, "agent_name": agent.name, "agent_id": agent.id}


@router.post("/{agent_id}/version")
async def bump_agent_version(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Bump agent version (patch increment)."""
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.status or "draft") != "published" or not agent.is_published:
        raise HTTPException(
            status_code=409,
            detail={"error": "agent_not_published"},
        )
    previous_version = agent.version or "1.0.0"
    agent.version = _bump_patch_version(previous_version)
    await _audit_agent_lifecycle(
        db,
        agent=agent,
        org=org,
        user=user,
        action="agent.lifecycle.versioned",
        details={
            "previous_version": previous_version,
            "version": agent.version,
            "status": "published",
        },
    )
    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


async def _owned_agent_for_lifecycle(
    agent_id: str,
    *,
    org: Organization,
    db: AsyncSession,
) -> Agent:
    agent = (
        await db.execute(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.organization_id == org.id,
                Agent.is_prebuilt.is_(False),
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/{agent_id}/publish")
async def publish_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Publish a draft Agent; publishing an already-live Agent is idempotent."""

    agent = await _owned_agent_for_lifecycle(agent_id, org=org, db=db)
    status = str(agent.status or "draft")
    if status == "archived":
        raise HTTPException(
            status_code=409,
            detail={"error": "agent_restore_required"},
        )
    if status != "published" or not agent.is_published:
        previous_status = status
        agent.status = "published"
        agent.is_published = True
        await _audit_agent_lifecycle(
            db,
            agent=agent,
            org=org,
            user=user,
            action="agent.lifecycle.published",
            details={
                "previous_status": previous_status,
                "status": "published",
                "version": agent.version or "1.0.0",
            },
        )
        await db.commit()
        await db.refresh(agent)
    return await _agent_to_dict(agent)


@router.post("/{agent_id}/archive")
async def archive_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Archive a project Agent and immediately disable all run transports."""

    agent = await _owned_agent_for_lifecycle(agent_id, org=org, db=db)
    status = str(agent.status or "draft")
    if status == "draft":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "agent_not_published",
                "message": "A draft Agent cannot be archived; publish or delete it.",
            },
        )
    if status != "archived" or agent.is_published:
        previous_status = status
        agent.status = "archived"
        agent.is_published = False
        await _audit_agent_lifecycle(
            db,
            agent=agent,
            org=org,
            user=user,
            action="agent.lifecycle.archived",
            details={
                "previous_status": previous_status,
                "status": "archived",
                "version": agent.version or "1.0.0",
            },
        )
        await db.commit()
        await db.refresh(agent)
    return await _agent_to_dict(agent)


@router.post("/{agent_id}/restore")
async def restore_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Restore an archived Agent to the published runnable state."""

    agent = await _owned_agent_for_lifecycle(agent_id, org=org, db=db)
    if str(agent.status or "draft") != "archived":
        raise HTTPException(
            status_code=409,
            detail={"error": "agent_not_archived"},
        )
    agent.status = "published"
    agent.is_published = True
    await _audit_agent_lifecycle(
        db,
        agent=agent,
        org=org,
        user=user,
        action="agent.lifecycle.restored",
        details={
            "previous_status": "archived",
            "status": "published",
            "version": agent.version or "1.0.0",
        },
    )
    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


# ---- Thread State (governed memory) ----
from app.services.thread_state import thread_manager

@router.post("/{agent_id}/threads")
async def create_thread(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a compatibility thread after verifying tenant ownership."""
    agent = (
        await db.execute(
            select(Agent.id).where(
                Agent.id == agent_id, Agent.organization_id == org.id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    thread = thread_manager.create(
        agent_id, user.id, organization_id=org.id,
    )
    return thread.to_dict()


@router.get("/{agent_id}/threads")
async def list_threads(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """List all threads for an agent."""
    return {
        "threads": thread_manager.list_by_agent(
            agent_id, user_id=user.id, organization_id=org.id,
        ),
        "persistence": "compatibility_memory_only",
        "production_surface": "/api/icoder/contexts",
    }


@router.get("/threads/stats")
async def thread_stats(
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Return only caller-owned compatibility thread counts."""
    threads = thread_manager.list_by_user(user.id)
    threads = [t for t in threads if t.get("organization_id") == org.id]
    return {
        "total_threads": len(threads),
        "active_threads": sum(t.get("status") == "active" for t in threads),
        "total_messages": sum(int(t.get("message_count") or 0) for t in threads),
        "persistence": "compatibility_memory_only",
    }


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Get a thread by ID."""
    thread = thread_manager.get(thread_id)
    if not thread or thread.user_id != user.id or thread.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread.to_dict()


@router.post("/threads/{thread_id}/snapshot")
async def snapshot_thread(
    thread_id: str,
    label: str = "",
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Save a snapshot of the current thread state."""
    thread = thread_manager.get(thread_id)
    if not thread or thread.user_id != user.id or thread.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Thread not found")
    snap = thread.save_snapshot(label)
    return {"thread_id": thread_id, "snapshot": snap}


@router.post("/threads/{thread_id}/restore")
async def restore_thread(
    thread_id: str,
    index: int = -1,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Restore thread state from a snapshot."""
    thread = thread_manager.get(thread_id)
    if not thread or thread.user_id != user.id or thread.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Thread not found")
    ok = thread.restore_snapshot(index)
    return {"thread_id": thread_id, "restored": ok, "state": thread.to_dict()}


# ---- Agent Execution (multi-Expert orchestration) ----

class AgentRunRequest(BaseModel):
    input: str = Field(..., min_length=1)
    conversation_history: list[dict] = []

@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: str,
    body: AgentRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an Agent with multi-Expert orchestration.

    Phase 2.1-A (2026-07-02): DEPRECATED for execution. The legacy
    ``agent_runner.run()`` path is removed; the new PlatformRuntime also
    no longer wraps an AgentRunner stub. Both paths now raise/redirect.

    New execution path: POST to the A2A endpoints exposed via
    ``mount_a2a`` in ``app/main.py`` (e.g. ``/a2a/v1/...``) — they route
    through the new ``InboundHandler`` orchestrator.

    This endpoint is retained for backward path-discovery: it returns
    410 Gone with a redirect message instead of a silent 500.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy Agent Definition execution was removed. Use "
            "POST /api/v1/agents/{runtime_agent_id}/run or "
            "POST /api/icoder/agents/{runtime_agent_id}/v1/message:send."
        ),
    )


@router.post("/{agent_id}/stream")
async def stream_agent(
    agent_id: str,
    body: AgentRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream Agent response via Server-Sent Events.

    Phase 2.1-A (2026-07-02): DEPRECATED. Returns 410 Gone — see
    ``run_agent`` above for the migration path.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy Agent Definition streaming was removed. Use "
            "POST /api/icoder/agents/{runtime_agent_id}/v1/message:stream."
        ),
    )


# ---- Analytics ----

@router.get("/stats/overall")
async def get_overall_stats(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate stats across all Agents."""
    return await agent_analytics.get_overall_stats(org.id, db)


@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get usage stats for a specific Agent."""
    return await agent_analytics.get_agent_stats(agent_id, org.id, db)


# ---- Agent Templates ----

_GENERIC_AGENT_TEMPLATES = [
    # Sprint 2 Goal A — Generic (non-medical) templates.
    # 这些模板刻意不依赖 MedCodER / ICD 编码 / 临床知识, 用于证明平台
    # 支持任意领域的 Agent 创建。expert_ids 为空, 不绑定任何医疗专家。
    {
        "id": "translator-blank",
        "title": "通用翻译智能体 (Generic Translator)",
        "description": "通用文本翻译，中英互译。无医疗依赖，无 MedCodER，无 ICD 编码。可作 Generic Agent 创建的起点。",
        "category": "通用",
        "icon": "Languages",
        "expert_ids": [],
        "config": {},
        "system_prompt": "<role>\nYou are a generic translation assistant. Translate text between Chinese and English. Preserve meaning, tone, and domain-specific terminology. No medical coding, no ICD lookup, no clinical reasoning.\n</role>\n\n<output_format>\nReturn only the translation. If the input is Chinese, translate to English. If English, translate to Chinese. If mixed, default to Chinese output.\n</output_format>"
    },
    {
        "id": "summarizer-blank",
        "title": "通用摘要智能体 (Generic Summarizer)",
        "description": "通用文档摘要，适用于任意领域文本。无医疗依赖，无 MedCodER，无 ICD 编码。",
        "category": "通用",
        "icon": "AlignLeft",
        "expert_ids": [],
        "config": {},
        "system_prompt": "<role>\nYou are a generic document summarization assistant. Given any input text, produce a concise summary covering key points. Domain-agnostic — no medical, legal, or financial specialization.\n</role>\n\n<output_format>\nSummary:\n1. One-sentence overview\n2. Key points (3-5 bullets)\n3. Action items (if any)\n</output_format>"
    },
]


def _visible_pack_for_template_id(template_id: str) -> dict | None:
    """Return a Hub-visible launch-candidate Pack for a template id."""

    from app.api.icoder_agents_hub import (
        load_visible_launch_candidate_packs,
        runtime_agent_id_from_ref,
    )

    for pack in load_visible_launch_candidate_packs():
        agent_id = runtime_agent_id_from_ref(str(pack.get("agent_ref") or ""))
        if agent_id == template_id:
            return pack
    return None


def _governed_template_from_pack(pack: dict) -> dict:
    """Project a canonical Pack into the New Agent template contract."""

    from app.api.icoder_agents_hub import runtime_agent_id_from_ref

    manifest = pack.get("manifest") or {}
    agent_ref = str(pack.get("agent_ref") or "")
    agent_id = runtime_agent_id_from_ref(agent_ref)
    experts = pack.get("experts") or []
    expert_ids = [
        str(item.get("expert_id") or item.get("id") or "").strip()
        for item in experts
        if isinstance(item, dict)
        and str(item.get("expert_id") or item.get("id") or "").strip()
    ]
    return {
        "id": agent_id,
        "title": str(manifest.get("name") or agent_id),
        "description": str(manifest.get("description") or ""),
        "category": str(
            manifest.get("category_display")
            or manifest.get("category")
            or "general"
        ),
        "icon": str(manifest.get("icon") or "Bot"),
        "expert_ids": expert_ids,
        # Kept for backward-compatible read-only previews. Creation must use
        # clone_transport below, never a generic Agent POST.
        "system_prompt": str(pack.get("system_prompt") or ""),
        "config": {},
        "template_kind": "governed_prebuilt",
        "clone_transport": "agent_hub",
        "clone_url": f"/api/icoder/agents/{agent_id}/clone",
        "source_agent_ref": agent_ref,
        "runtime_agent_id": agent_id,
        "version": str(manifest.get("version") or "1.0.0"),
        "human_review": str(manifest.get("human_review") or "required"),
        "production_ready": bool(manifest.get("production_ready", False)),
        "non_goals": list(pack.get("non_goals") or []),
    }


def get_agent_template_catalog() -> list[dict]:
    """Build templates from the exact current Hub visibility boundary."""

    from app.api.icoder_agents_hub import load_visible_launch_candidate_packs

    governed = [
        _governed_template_from_pack(pack)
        for pack in load_visible_launch_candidate_packs()
    ]
    governed.sort(key=lambda item: item["id"])
    generic = [
        dict(template)
        for template in _GENERIC_AGENT_TEMPLATES
    ]
    for template in generic:
        template["template_kind"] = "generic_blank"
        template["clone_transport"] = "generic_create"
    return governed + generic


# Compatibility export for tests and internal imports. Endpoints call the
# builder so pack changes are reflected without another hand-maintained list.
AGENT_TEMPLATES = get_agent_template_catalog()


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Delete agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_prebuilt:
        raise HTTPException(status_code=403, detail="Cannot delete prebuilt agents")
    await _audit_agent_lifecycle(
        db,
        agent=agent,
        org=org,
        user=user,
        action="agent.lifecycle.deleted",
        details={
            "status": agent.status or "draft",
            "version": agent.version or "1.0.0",
        },
    )
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted"}
