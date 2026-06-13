"""RuntimeAgentRegistry — persistent-ish registry of thin Agent definitions.

A thin Agent is a role (systemPrompt) + a list of Expert ids it may call. All domain
capability lives in the Experts (coding-expert), mirroring Corti's agents×experts split.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentDefinition:
    id: str
    name: str
    version: str
    category: str
    experts: list[str]
    system_prompt: str
    non_goals: list[str] = field(default_factory=list)
    output_contract: str = ""
    rule_sets: list[str] = field(default_factory=lambda: ["medical_coding"])


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._agents.get(agent_id)

    def list(self) -> list[AgentDefinition]:
        return list(self._agents.values())


def default_registry() -> AgentRegistry:
    from ..agents.homepage_coding_review import AGENT as CODING_AGENT
    from ..agents.drg_grouping_review import AGENT as DRG_AGENT
    from ..agents.revenue_compliance_review import AGENT as REVENUE_AGENT

    reg = AgentRegistry()
    reg.register(CODING_AGENT)
    reg.register(DRG_AGENT)
    reg.register(REVENUE_AGENT)
    return reg
