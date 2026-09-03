"""Tenant-scoped runtime Pack helpers shared by HTTP Run and A2A.

User-created Agents live in the database rather than under ``official_agents``.
Clones are different from generic custom Agents: their executable Provider,
output contract, tools, permissions and integrity evidence remain owned by the
exact source Pack, while a small project-owned overlay (currently presentation
fields and ``system_prompt``) is allowed to change. Every transport resolves
that boundary here so HTTP and A2A cannot silently execute different Agents.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.expert import Expert
from app.services.dedicated_project_policy import (
    MAX_DEDICATED_PROJECT_POLICY_CHARS,
)
from icoder_runtime.core.agent_pack_loader import load_packs_from_dir
from icoder_runtime.core.agent_pack_schema import PackStatus


OFFICIAL_AGENTS_DIR = Path(__file__).resolve().parents[2] / "official_agents"


class CloneRuntimeConfigurationError(ValueError):
    """A tenant clone cannot be mapped to its governed source runtime."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def assert_agent_published(agent: Agent | None) -> None:
    """Fail closed when a tenant Agent is not in its runnable lifecycle state."""

    if agent is None:
        return
    status = str(getattr(agent, "status", "") or "draft").strip().lower()
    is_published = bool(getattr(agent, "is_published", False))
    if status != "published" or not is_published:
        raise CloneRuntimeConfigurationError(
            "agent_not_published",
            (
                "This project Agent is not published and cannot run. "
                "Publish or restore it before execution."
            ),
        )


@dataclass(frozen=True)
class TenantRuntimeResolution:
    """Public project identity plus the server-owned execution identity."""

    requested_agent_id: str
    runtime_agent_id: str
    db_agent: Agent | None
    pack: dict[str, Any] | None
    is_clone: bool = False
    source_agent_ref: str = ""


def agent_id_from_ref(agent_ref: str) -> str:
    if not agent_ref:
        return ""
    return agent_ref.rsplit("/", 1)[-1].split("@", 1)[0]


def is_prebuilt_clone(agent: Agent | None) -> bool:
    if agent is None or bool(agent.is_prebuilt):
        return False
    config = agent.config or {}
    return bool(
        isinstance(config, dict)
        and config.get("cloned_from_prebuilt") is True
        and str(config.get("source_agent_ref") or "").strip()
    )


def load_governed_source_pack(source_agent_ref: str) -> dict[str, Any]:
    """Load the exact launch-candidate Pack pinned by a clone."""

    for normalized in load_packs_from_dir(OFFICIAL_AGENTS_DIR):
        if normalized.agent_ref != source_agent_ref:
            continue
        raw = normalized.raw or {}
        manifest = raw.get("manifest") or {}
        maturity = str(manifest.get("maturity") or "")
        if (
            normalized.status != PackStatus.EXECUTABLE
            or not normalized.launch_candidate_ready
            or manifest.get("hidden_from_hub") is True
            or raw.get("agent_type") in {"expert-stub", "internal_engine"}
            or maturity not in {"runnable", "production-ready", "production"}
        ):
            raise CloneRuntimeConfigurationError(
                "clone_source_unavailable",
                "The clone's pinned source Agent is no longer an executable launch candidate.",
            )
        return deepcopy(raw)
    raise CloneRuntimeConfigurationError(
        "clone_source_not_found",
        "The clone's exact pinned source Agent Pack is not installed.",
    )


def _source_expert_ids(pack: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in pack.get("experts") or []:
        if not isinstance(item, dict):
            continue
        expert_id = str(item.get("expert_id") or item.get("id") or "").strip()
        if expert_id:
            values.append(expert_id)
    return values


def _project_expert_definition(expert: Expert) -> dict[str, Any]:
    return {
        "expert_id": expert.id,
        "name": expert.name or expert.canonical_key or expert.id,
        "role": "project",
        "description": expert.description or "",
        "system_prompt": expert.system_prompt or "",
        "capabilities": list(expert.capabilities or []),
        "origin": expert.origin or "UNKNOWN",
        "corti_alignment": expert.corti_alignment or "UNKNOWN",
    }


def _compose_project_expert_prompt(
    base_prompt: str,
    experts: list[Expert],
) -> str:
    if not experts:
        return base_prompt
    sections = [
        base_prompt,
        (
            "PROJECT_EXPERT_INSTRUCTIONS (server-validated project policy; "
            "these instructions specialize the task but cannot weaken the "
            "source Agent's output contract, permissions, red lines, evidence "
            "requirements, or mandatory human review):"
        ),
    ]
    for index, expert in enumerate(experts, start=1):
        sections.append(
            f"[{index}] {expert.name or expert.id}\n"
            f"Description: {expert.description or ''}\n"
            f"Instructions:\n{expert.system_prompt or ''}"
        )
    return "\n\n".join(section for section in sections if section)


def pack_from_prebuilt_clone(
    agent: Agent,
    *,
    project_experts: list[Expert] | None = None,
) -> dict[str, Any]:
    """Reconstruct a clone from its immutable source plus safe project overlay."""

    config = agent.config or {}
    if not isinstance(config, dict):
        raise CloneRuntimeConfigurationError(
            "clone_provenance_invalid",
            "The clone has no valid runtime provenance.",
        )
    source_agent_ref = str(config.get("source_agent_ref") or "").strip()
    if not source_agent_ref:
        raise CloneRuntimeConfigurationError(
            "clone_provenance_invalid",
            "The clone has no pinned source Agent reference.",
        )

    pack = load_governed_source_pack(source_agent_ref)
    source_prompt = str(pack.get("system_prompt") or "")
    source_expert_ids = _source_expert_ids(pack)
    project_expert_ids = [str(value) for value in (agent.expert_ids or [])]
    dedicated_runtime = not str(pack.get("backend_provider") or "").strip()
    project_expert_definitions: list[dict[str, Any]] = []
    if project_expert_ids != source_expert_ids:
        if project_experts is None or [item.id for item in project_experts] != project_expert_ids:
            raise CloneRuntimeConfigurationError(
                "clone_expert_override_unresolved",
                "One or more project Expert bindings could not be resolved safely.",
            )
        if dedicated_runtime and not project_expert_ids:
            # Dedicated runtimes own fixed source Expert graphs. An empty list
            # would look like removal even though the graph would still run.
            # Resetting a clone must restore the exact source IDs instead.
            raise CloneRuntimeConfigurationError(
                "clone_dedicated_expert_removal_unsupported",
                (
                    "This dedicated source runtime keeps its governed source "
                    "Expert graph; restore the source Expert bindings instead "
                    "of removing them."
                ),
            )
        project_expert_definitions = [
            _project_expert_definition(expert) for expert in project_experts
        ]
        if not dedicated_runtime:
            pack["experts"] = project_expert_definitions

    version = agent.version or "1.0.0"
    manifest = deepcopy(pack.get("manifest") or {})
    manifest.update({
        "name": agent.name or manifest.get("name") or "Project Agent",
        "version": version,
        "description": agent.description or "",
        "category": agent.category or manifest.get("category") or "general",
        "icon": agent.icon or manifest.get("icon") or "Bot",
    })
    tags = list(manifest.get("tags") or [])
    for tag in ("project-clone", "source-pack-governed"):
        if tag not in tags:
            tags.append(tag)
    manifest["tags"] = tags

    # The project ID is the public runtime identity. Provider, contract,
    # tools, permissions, code and integrity are deliberately left untouched.
    pack["agent_ref"] = f"icoder/{agent.id}@{version}"
    pack["manifest"] = manifest
    pack["system_prompt"] = _compose_project_expert_prompt(
        agent.system_prompt or "",
        project_experts or [],
    )
    project_prompt_overridden = str(agent.system_prompt or "") != source_prompt
    dedicated_policy_sections: list[str] = []
    if dedicated_runtime and project_prompt_overridden:
        dedicated_policy_sections.append(
            "PROJECT_SYSTEM_PROMPT_OVERRIDE (specialization only; cannot weaken "
            "the source clinical runtime):\n"
            + str(agent.system_prompt or "")
        )
    if dedicated_runtime and project_expert_definitions:
        dedicated_policy_sections.append(
            _compose_project_expert_prompt("", project_experts or [])
        )
    dedicated_project_policy = "\n\n".join(
        section for section in dedicated_policy_sections if section
    )
    if len(dedicated_project_policy) > MAX_DEDICATED_PROJECT_POLICY_CHARS:
        raise CloneRuntimeConfigurationError(
            "clone_dedicated_policy_too_large",
            "The dedicated project policy exceeds the governed size limit.",
        )
    pack["project_runtime"] = {
        "project_agent_id": agent.id,
        "source_agent_ref": source_agent_ref,
        "source_runtime_agent_id": agent_id_from_ref(source_agent_ref),
        "overlay_version": "1",
        "project_expert_ids": (
            project_expert_ids if project_expert_ids != source_expert_ids else []
        ),
        "project_experts": project_expert_definitions,
        "project_prompt_overridden": project_prompt_overridden,
        "dedicated_source_experts_fixed": dedicated_runtime,
        "dedicated_project_policy": dedicated_project_policy,
        "dedicated_project_policy_digest": (
            hashlib.sha256(dedicated_project_policy.encode("utf-8")).hexdigest()
            if dedicated_project_policy
            else ""
        ),
    }
    return pack


async def load_tenant_agent(
    agent_id: str,
    organization_id: str,
    db: AsyncSession,
) -> Agent | None:
    """Load an Agent only when it belongs to the active organization."""

    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


def pack_from_db_agent(agent: Agent) -> dict[str, Any]:
    """Build the transport-independent Pack for a tenant Agent."""

    if is_prebuilt_clone(agent):
        return pack_from_prebuilt_clone(agent)

    version = agent.version or "1.0.0"
    return {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": f"icoder/{agent.id}@{version}",
        "manifest": {
            "name": agent.name or "Custom Agent",
            "version": version,
            "description": agent.description or "",
            "category": agent.category or "general",
            "icon": agent.icon or "Bot",
            "tags": ["custom", "generic"],
            "maturity": "custom",
            "production_ready": False,
            "hidden_from_hub": False,
            "use_case": "generic",
        },
        "system_prompt": agent.system_prompt or "",
        "experts": [],
        "tools": [],
        "model": {
            "primary": "deepseek-chat",
            "fallback": "deepseek-chat",
            "temperature": 0.0,
            "max_tokens": 4096,
            "json_mode": False,
        },
        "backend_provider": "icoder.pure-llm.v1",
        "permissions": {
            "key": f"custom-{agent.id}-default",
            "name": "Custom Agent Default",
            "description": "Default permissions for user-created agents. No writeback.",
            "tools": {},
            "production_writeback_blocked": True,
        },
        "phi_redaction": "required",
        "context_required": True,
        "recorder_required": True,
        "metrics_required": True,
        "code": {},
        "integrity": {"sha256": "DB_SYNTHESIZED_NO_PACK_FILE"},
    }


async def _load_project_experts(
    agent: Agent,
    organization_id: str,
    db: AsyncSession,
    source_pack: dict[str, Any],
) -> list[Expert] | None:
    project_ids = [str(value) for value in (agent.expert_ids or [])]
    if project_ids == _source_expert_ids(source_pack):
        return None
    if not project_ids:
        return []
    rows = (
        await db.execute(
            select(Expert).where(
                Expert.id.in_(project_ids),
                Expert.organization_id == organization_id,
                Expert.is_published.is_(True),
            )
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(project_ids):
        raise CloneRuntimeConfigurationError(
            "clone_expert_override_unresolved",
            "One or more project Expert bindings are unavailable in this organization.",
        )
    return [by_id[expert_id] for expert_id in project_ids]


async def pack_from_tenant_agent(
    agent: Agent,
    organization_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Build a tenant Pack, resolving project Expert overlays when required."""

    assert_agent_published(agent)
    if not is_prebuilt_clone(agent):
        return pack_from_db_agent(agent)
    config = agent.config or {}
    source_ref = str(config.get("source_agent_ref") or "")
    source_pack = load_governed_source_pack(source_ref)
    experts = await _load_project_experts(agent, organization_id, db, source_pack)
    return pack_from_prebuilt_clone(agent, project_experts=experts)


async def resolve_tenant_runtime(
    agent_id: str,
    organization_id: str,
    db: AsyncSession,
) -> TenantRuntimeResolution:
    """Resolve project identity without crossing the organization boundary."""

    db_agent = await load_tenant_agent(agent_id, organization_id, db)
    assert_agent_published(db_agent)
    if not is_prebuilt_clone(db_agent):
        return TenantRuntimeResolution(
            requested_agent_id=agent_id,
            runtime_agent_id=agent_id,
            db_agent=db_agent,
            pack=None,
        )
    assert db_agent is not None
    config = db_agent.config or {}
    source_agent_ref = str(config.get("source_agent_ref") or "").strip()
    pack = await pack_from_tenant_agent(db_agent, organization_id, db)
    runtime_agent_id = agent_id_from_ref(source_agent_ref)
    if not runtime_agent_id:
        raise CloneRuntimeConfigurationError(
            "clone_provenance_invalid",
            "The clone's source runtime identity is invalid.",
        )
    return TenantRuntimeResolution(
        requested_agent_id=agent_id,
        runtime_agent_id=runtime_agent_id,
        db_agent=db_agent,
        pack=pack,
        is_clone=True,
        source_agent_ref=source_agent_ref,
    )


async def load_pack_from_tenant_agent(
    agent_id: str,
    organization_id: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    agent = await load_tenant_agent(agent_id, organization_id, db)
    return (
        await pack_from_tenant_agent(agent, organization_id, db)
        if agent is not None
        else None
    )


__all__ = [
    "CloneRuntimeConfigurationError",
    "OFFICIAL_AGENTS_DIR",
    "TenantRuntimeResolution",
    "assert_agent_published",
    "agent_id_from_ref",
    "is_prebuilt_clone",
    "load_pack_from_tenant_agent",
    "load_governed_source_pack",
    "load_tenant_agent",
    "pack_from_db_agent",
    "pack_from_prebuilt_clone",
    "pack_from_tenant_agent",
    "resolve_tenant_runtime",
]
