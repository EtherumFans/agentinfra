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
    # Which UI/run surface this agent drives. Left empty for back-compat: rule_sets alone
    # distinguished extract (none) from coding-review (some). Phase 2 added tool agents that
    # ALSO have no rule_sets, so the surface must be stated explicitly on those — see
    # effective_surface() for the derivation.
    surface: str = ""


def effective_surface(agent: AgentDefinition) -> str:
    """Resolve an agent's surface: explicit field wins; otherwise derive from rule_sets
    (no rule sets = pure fact/abstraction = extract; otherwise the full coding-review run).
    The tool agents set surface="tool" explicitly since they also carry no rule sets."""
    if agent.surface:
        return agent.surface
    return "extract" if not agent.rule_sets else "coding-review"


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
    from ..agents.fact_extraction import AGENT as EXTRACT_AGENT
    from ..agents.homepage_coding_review import AGENT as CODING_AGENT
    from ..agents.drg_grouping_review import AGENT as DRG_AGENT
    from ..agents.revenue_compliance_review import AGENT as REVENUE_AGENT
    # Phase 2 atomic tool agents (surface="tool"): prose research reports on the executor.
    from ..agents.index_navigation import AGENT as INDEX_NAV_AGENT
    from ..agents.code_validation import AGENT as CODE_VALIDATION_AGENT
    from ..agents.compliance_guardrail import AGENT as GUARDRAIL_AGENT
    from ..agents.document_standardization import AGENT as DOC_STD_AGENT

    reg = AgentRegistry()
    reg.register(EXTRACT_AGENT)
    reg.register(CODING_AGENT)
    reg.register(DRG_AGENT)
    reg.register(REVENUE_AGENT)
    reg.register(INDEX_NAV_AGENT)
    reg.register(CODE_VALIDATION_AGENT)
    reg.register(GUARDRAIL_AGENT)
    reg.register(DOC_STD_AGENT)
    return reg
