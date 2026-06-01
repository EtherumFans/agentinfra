"""Tools API — discover, register, and inspect Agent tools with contracts.

GET    /api/tools               — List all tools
POST   /api/tools               — Register a custom tool
GET    /api/tools/categories    — List categories with counts
GET    /api/tools/permission-presets — List permission presets
GET    /api/tools/{id}          — Get tool definition
DELETE /api/tools/{id}          — Unregister a custom tool
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware.auth import get_current_user
from app.models.user import User
from app.tools import register_all_tools, get_registry_summary
from app.services.tool_registry import tool_registry, ToolDefinition, ToolTier

router = APIRouter(prefix="/api/tools", tags=["tools"])

# Ensure tools are registered on first API call
_tools_registered = False


def _ensure_registered():
    global _tools_registered
    if not _tools_registered:
        register_all_tools()
        _tools_registered = True


@router.get("")
async def list_tools(category: str | None = None, tier: int | None = None):
    """List all available tools, optionally filtered by category or tier."""
    _ensure_registered()

    tools = tool_registry.list_all()
    if category:
        tools = tool_registry.list_by_category(category)
    if tier is not None:
        from app.services.tool_registry import ToolTier
        tools = [t for t in tools if t.tier == ToolTier(tier)]

    return {
        "tools": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "tier": t.tier.value,
                "category": t.category,
                "icon": t.icon,
                "requires": t.requires,
                "guarantees": t.guarantees,
                "accuracy_tags": t.accuracy_tags,
                "is_injectable": t.is_injectable,
                "has_input_schema": t.input_schema is not None,
            }
            for t in tools
        ],
    }


@router.get("/permission-presets")
async def list_permission_presets():
    """List available permission policy presets for Agent creation."""
    from app.services.permissions import PRESET_POLICIES
    return {
        "presets": [
            {
                "key": key,
                "name": info["name"],
                "description": info["description"],
                "tool_count": len(info["policy"].permissions),
                "tools": list(info["policy"].permissions.keys()),
            }
            for key, info in PRESET_POLICIES.items()
        ],
    }


@router.get("/categories")
async def list_categories():
    """List all tool categories with counts."""
    _ensure_registered()
    summary = get_registry_summary()
    return {
        "categories": {
            cat: {
                "count": len(tools),
                "tier1_count": sum(1 for t in tools if t["tier"] == 1),
                "tier2_count": sum(1 for t in tools if t["tier"] == 2),
            }
            for cat, tools in summary["categories"].items()
        },
        "total_tools": summary["total_tools"],
        "tier1_total": summary["tier1_count"],
        "tier2_total": summary["tier2_count"],
    }


@router.get("/{tool_id}")
async def get_tool(tool_id: str):
    """Get a single tool definition by ID."""
    _ensure_registered()
    tool = tool_registry.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    return {
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "tier": tool.tier.value,
        "category": tool.category,
        "icon": tool.icon,
        "requires": tool.requires,
        "guarantees": tool.guarantees,
        "accuracy_tags": tool.accuracy_tags,
        "is_injectable": tool.is_injectable,
        "input_schema": tool.input_schema,
    }


# ── Custom Tool Registration ──

class ToolParamSpec(BaseModel):
    type: str = "string"
    required: bool = True
    description: str = ""


class ToolRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    tier: int = Field(default=1, ge=1, le=2)
    icon: str = "Wrench"
    requires: str = ""
    guarantees: str = ""
    params: dict[str, dict] = Field(default_factory=dict)
    accuracy_tags: list[str] = Field(default_factory=list)
    is_injectable: bool = False


@router.post("", status_code=201)
async def register_custom_tool(
    body: ToolRegisterRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a custom tool with contract metadata.

    The tool is loaded into the runtime registry immediately.
    Contract enforcement (pre/post conditions) applies during Agent execution.
    External tools execute via LLM — no Python executor is required.
    """
    import uuid

    _ensure_registered()
    tool_id = f"custom-{uuid.uuid4().hex[:10]}"

    td = ToolDefinition(
        id=tool_id,
        name=body.name,
        description=body.description,
        tier=ToolTier(body.tier),
        category=body.category,
        icon=body.icon,
        requires=[body.requires] if body.requires else [],
        guarantees={"output": body.guarantees} if body.guarantees else {},
        input_schema={
            "type": "object",
            "properties": body.params,
        } if body.params else None,
        accuracy_tags=body.accuracy_tags,
        is_injectable=body.is_injectable,
        executor=None,  # External tools execute via LLM
    )

    tool_registry.register(td)

    return {
        "id": td.id,
        "name": td.name,
        "description": td.description,
        "tier": td.tier.value,
        "category": td.category,
        "icon": td.icon,
        "requires": td.requires,
        "guarantees": td.guarantees,
        "params": body.params,
        "accuracy_tags": td.accuracy_tags,
        "is_injectable": td.is_injectable,
        "registered": True,
    }


@router.delete("/{tool_id}")
async def unregister_custom_tool(
    tool_id: str,
    user: User = Depends(get_current_user),
):
    """Unregister a custom tool. Built-in tools cannot be removed."""
    _ensure_registered()

    if not tool_id.startswith("custom-"):
        raise HTTPException(status_code=403, detail="Cannot remove built-in tools")

    if tool_id not in tool_registry:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool_registry._tools.pop(tool_id, None)
    return {"status": "removed", "tool_id": tool_id}
