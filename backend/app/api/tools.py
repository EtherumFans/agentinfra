"""Tools API — discover and inspect available Agent tools with contracts.

GET /api/tools          — List all available tools
GET /api/tools/categories — List categories with tool counts
GET /api/tools/{id}     — Get a single tool definition
"""

from fastapi import APIRouter, HTTPException
from app.tools import register_all_tools, get_registry_summary
from app.services.tool_registry import tool_registry

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
