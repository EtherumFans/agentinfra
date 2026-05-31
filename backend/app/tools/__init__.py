"""iCoDer Tools — Contract-enforced capabilities for Agent Runtime.

Each tool is a self-contained capability with Hoare-style {P} t {Q} contracts:
- Preconditions (P): what must be true in SymbolicState before calling
- Postconditions (Q): what the tool guarantees about its output

Tier 1 (deterministic): Zero LLM — ICD index, evidence ranking, calibration, guardrails
Tier 2 (LLM-powered): LLM for reasoning — extraction, code assignment, report generation

Usage:
    from app.tools import tool_registry, register_all_tools
    register_all_tools()
    result = await tool_registry.execute("search_icd10_index", {"term": "pneumonia"})
"""

# Legacy tool functions (imported by other modules)
from app.tools.search_codes import search_codes_tool
from app.tools.explore_code import explore_code_tool
from app.tools.retrieve_rules import retrieve_rules_tool
from app.tools.verify_sequence import verify_sequence_tool

# Contract-enforced tool registry
from app.services.tool_registry import tool_registry, ToolDefinition, ToolTier
from .safety_tools import SAFETY_TOOLS
from .extraction_tools import EXTRACTION_TOOLS
from .coding_tools import CODING_TOOLS
from .verification_tools import VERIFICATION_TOOLS
from .analysis_tools import ANALYSIS_TOOLS
from .report_tools import REPORT_TOOLS

__all__ = [
    # Legacy exports
    "search_codes_tool",
    "explore_code_tool",
    "retrieve_rules_tool",
    "verify_sequence_tool",
    # Contract tool exports
    "tool_registry",
    "ToolDefinition",
    "ToolTier",
    "register_all_tools",
    "get_registry_summary",
]


def register_all_tools() -> None:
    """Register all built-in tools into the global registry.

    Called once at application startup. Idempotent — re-registering
    overwrites previous definitions for the same tool ID.
    """
    all_tools = (
        SAFETY_TOOLS
        + EXTRACTION_TOOLS
        + CODING_TOOLS
        + VERIFICATION_TOOLS
        + ANALYSIS_TOOLS
        + REPORT_TOOLS
    )

    for tool in all_tools:
        tool_registry.register(tool)

    import logging
    logger = logging.getLogger(__name__)
    tier1 = len(tool_registry.list_by_tier(ToolTier.DETERMINISTIC))
    tier2 = len(tool_registry.list_by_tier(ToolTier.LLM_REASONING))
    logger.info(
        f"Registered {len(all_tools)} tools: {tier1} Tier 1 (deterministic), "
        f"{tier2} Tier 2 (LLM-powered)"
    )


def get_registry_summary() -> dict:
    """Get a summary of all registered tools for API responses."""
    categories = tool_registry.get_categories()
    return {
        "total_tools": len(tool_registry),
        "tier1_count": len(tool_registry.list_by_tier(ToolTier.DETERMINISTIC)),
        "tier2_count": len(tool_registry.list_by_tier(ToolTier.LLM_REASONING)),
        "categories": {
            cat: [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "tier": t.tier.value,
                    "icon": t.icon,
                    "requires": t.requires,
                    "guarantees": t.guarantees,
                    "accuracy_tags": t.accuracy_tags,
                    "is_injectable": t.is_injectable,
                }
                for t in tools
            ]
            for cat, tools in categories.items()
        },
    }
