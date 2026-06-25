"""M2 — tool_registry tests (~5 cases).

Asserts:
  - TOOL_REGISTRY has exactly 5 tools
  - Names match the Agent Pack's ``tools`` array
  - Each tool has inputSchema + outputSchema (JSON Schema objects)
  - Each handler_ref resolves to an importable async callable
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.icoder.mcp.tool_registry import (
    TOOL_REGISTRY,
    assert_tool_registry_matches_agent_pack,
)


# ── Path to Agent Pack (for boot-time assertion test) ──


# File layout: backend/tests/unit/icoder/mcp/test_tool_registry.py
# → backend/official_agents/medcoder-coding-review/agent_pack.json
# 4 levels up (tests/unit/icoder/mcp → backend).
_AGENT_PACK_PATH = (
    Path(__file__).resolve().parents[4]
    / "official_agents"
    / "medcoder-coding-review"
    / "agent_pack.json"
)


def _agent_pack_tools() -> list[dict]:
    """Load ``tools`` array from the Agent Pack JSON."""
    import json

    return json.loads(_AGENT_PACK_PATH.read_text(encoding="utf-8"))["tools"]


# ── Tests ──


def test_tool_registry_has_exactly_5_tools():
    """M2 ships exactly 5 MCP tools (audit Part 7.4)."""
    assert len(TOOL_REGISTRY) == 5
    assert set(TOOL_REGISTRY) == {
        "search_icd",
        "verify_code",
        "get_differentiation_hint",
        "rerank_codes",
        "calibrate_confidence",
    }


def test_tool_registry_names_match_agent_pack():
    """The Python registry and the Agent Pack JSON must agree on names."""
    declared = {t["name"] for t in _agent_pack_tools()}
    assert set(TOOL_REGISTRY) == declared, (
        f"registry ({set(TOOL_REGISTRY)}) != agent_pack ({declared}); "
        "update either side to match."
    )


def test_each_tool_has_input_and_output_schema():
    """Every tool descriptor has a non-empty inputSchema and outputSchema."""
    for name, desc in TOOL_REGISTRY.items():
        assert isinstance(desc.input_schema, dict), f"{name} input_schema"
        assert isinstance(desc.output_schema, dict), f"{name} output_schema"
        # Pydantic-generated schemas always include a ``type`` key.
        assert desc.input_schema.get("type") == "object", f"{name} input"
        assert desc.output_schema.get("type") == "object", f"{name} output"
        # inputSchema must have a ``properties`` key.
        assert "properties" in desc.input_schema, f"{name} input.properties"


def test_each_handler_ref_resolves_to_callable():
    """Every ``handler_ref`` (``module:func``) imports cleanly."""
    from app.icoder.mcp.server import resolve_handler

    for name, desc in TOOL_REGISTRY.items():
        handler = resolve_handler(desc.handler_ref)
        assert callable(handler), f"{name} handler not callable"
        import inspect
        assert inspect.iscoroutinefunction(handler), (
            f"{name} handler must be async def"
        )


def test_assert_tool_registry_matches_agent_pack_passes_for_real_pack():
    """The boot-time assertion must succeed against the real Agent Pack."""
    assert_tool_registry_matches_agent_pack(_agent_pack_tools())  # no raise


def test_assert_tool_registry_matches_agent_pack_fails_on_mismatch():
    """When the registry and Agent Pack disagree, the assertion raises."""
    fake_tools = [{"name": "totally_made_up_tool"}]
    with pytest.raises(AssertionError, match="TOOL_REGISTRY"):
        assert_tool_registry_matches_agent_pack(fake_tools)