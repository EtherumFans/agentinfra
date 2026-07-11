"""CapabilityRegistry — explicit registry of Experts + Tools (§8.1).

Wraps AgentDefinition.expert_ids + the ToolRegistry into a single
lookup. The Planner queries this to know which capabilities exist
before generating a plan.

Per §8.1 this is the "CapabilityRegistry" component — currently the
information is implicit (scattered across agent_provider + agent packs'
expert_ids field). This module makes it explicit so the Planner can
answer:

  - "which experts can agent X invoke?"
  - "what tools does expert Y expose?"
  - "is capability Z available at all?"

Resolution order for ``lookup_expert(expert_id)``:
  1. Runtime AgentRegistry (real Experts from agent packs)
  2. Back-compat stub registry (Phase-1 placeholder)

Tool resolution:
  1. MCP server registry (real MCP tools)
  2. icoder_runtime.backends.tool_mcp_compat_layer

Both fall through to ``None`` if no match — the Planner/PolicyGuard
decides whether to fail or proceed with reduced capability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ExpertCapability:
    """One registered Expert capability."""

    expert_id: str
    display_name: str = ""
    description: str = ""
    tool_ids: list[str] = field(default_factory=list)
    runtime_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCapability:
    """One registered Tool capability."""

    tool_id: str
    expert_id: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    invocation_cost_cny: float = 0.0


class CapabilityRegistry:
    """Explicit Expert + Tool capability lookup for the Planner.

    Construct once at lifespan startup, query per run. The registry is
    populated from AgentRegistry + MCP server introspection.
    """

    def __init__(self) -> None:
        self._experts: dict[str, ExpertCapability] = {}
        self._tools: dict[str, ToolCapability] = {}
        self._agent_experts: dict[str, list[str]] = {}

    def register_expert(self, capability: ExpertCapability) -> None:
        self._experts[capability.expert_id] = capability

    def register_tool(self, capability: ToolCapability) -> None:
        self._tools[capability.tool_id] = capability

    def bind_expert_to_agent(self, agent_id: str, expert_ids: list[str]) -> None:
        self._agent_experts[agent_id] = list(expert_ids or [])

    def lookup_expert(self, expert_id: str) -> ExpertCapability | None:
        return self._experts.get(expert_id)

    def lookup_tool(self, tool_id: str) -> ToolCapability | None:
        return self._tools.get(tool_id)

    def experts_for_agent(self, agent_id: str) -> list[ExpertCapability]:
        ids = self._agent_experts.get(agent_id, [])
        out: list[ExpertCapability] = []
        for eid in ids:
            cap = self._experts.get(eid)
            if cap is not None:
                out.append(cap)
        return out

    def expert_ids_for_agent(self, agent_id: str) -> list[str]:
        return list(self._agent_experts.get(agent_id, []))

    def all_expert_ids(self) -> list[str]:
        return sorted(self._experts.keys())

    def all_tool_ids(self) -> list[str]:
        return sorted(self._tools.keys())


def build_capability_registry_from_agent_provider(
    agent_provider: Callable[[str], Any],
    *,
    agent_ids: list[str] | None = None,
) -> CapabilityRegistry:
    """Scan an agent_provider and populate the registry.

    For each agent in ``agent_ids``, extracts ``expert_ids`` from the
    AgentDefinition and creates stub ExpertCapability entries. Real
    metadata (tool bindings, schemas) is filled in later by the
    lifespan's MCP introspection step.
    """
    registry = CapabilityRegistry()
    for agent_id in agent_ids or []:
        try:
            agent = agent_provider(agent_id)
        except Exception:
            continue
        if agent is None:
            continue
        expert_ids = list(getattr(agent, "expert_ids", []) or [])
        registry.bind_expert_to_agent(agent_id, expert_ids)
        for eid in expert_ids:
            if registry.lookup_expert(eid) is None:
                registry.register_expert(
                    ExpertCapability(
                        expert_id=eid,
                        display_name=eid,
                        description=f"Auto-registered from agent {agent_id}",
                    )
                )
    return registry


__all__ = [
    "CapabilityRegistry",
    "ExpertCapability",
    "ToolCapability",
    "build_capability_registry_from_agent_provider",
]
