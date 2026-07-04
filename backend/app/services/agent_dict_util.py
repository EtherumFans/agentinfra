"""Shared util for serializing Agent model → dict.

Extracted from app/api/agents.py during Phase 2.1-B Step 3 so that admin.py
and any future caller can serialize Agents without importing a deleted router.
"""
from app.models.agent import Agent


async def agent_to_dict(agent: Agent) -> dict:
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
        "is_prebuilt": agent.is_prebuilt,
        "is_published": agent.is_published,
        "version": agent.version or "1.0.0",
        "status": agent.status or "draft",
        "created_by": agent.created_by,
        "usage_count": agent.usage_count or 0,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }
