"""default_registry + effective_surface — the 3-way surface derivation.

The registry holds 8 thin agents across 3 surfaces. effective_surface is the single source
of truth the API/UI branch on: explicit `surface` field wins; otherwise it derives from
rule_sets (none = extract, some = coding-review) for back-compat with the original two agents.
"""
from icoder.runtime.registry import default_registry, effective_surface

EXPECTED = {
    "icoder/diagnostic-entity-extractor-agent": "extract",
    "icoder/homepage-coding-review-agent": "coding-review",
    "icoder/drg-grouping-review-agent": "coding-review",
    "icoder/revenue-compliance-review-agent": "coding-review",
    "icoder/icd-index-navigator-agent": "tool",
    "icoder/code-validation-agent": "tool",
    "icoder/compliance-guardrail-agent": "tool",
    "icoder/document-semantic-standardization-agent": "tool",
}


def test_registry_holds_all_eight_agents():
    reg = default_registry()
    assert {a.id for a in reg.list()} == set(EXPECTED)


def test_effective_surface_for_each_agent():
    reg = default_registry()
    for agent_id, surface in EXPECTED.items():
        agent = reg.get(agent_id)
        assert agent is not None, agent_id
        assert effective_surface(agent) == surface, agent_id


def test_tool_agents_carry_explicit_surface_and_no_rule_sets():
    reg = default_registry()
    for agent_id, surface in EXPECTED.items():
        if surface != "tool":
            continue
        agent = reg.get(agent_id)
        assert agent.surface == "tool"  # explicit, not derived
        assert agent.rule_sets == []  # tool agents carry no rule sets (like extract)
        assert agent.experts == ["coding-expert"]
