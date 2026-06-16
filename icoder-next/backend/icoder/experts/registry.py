"""ExpertRegistry — the capability side of the agents×experts split.

An Expert is a named, reusable unit of domain capability (knowledge + tools). Thin
Agents do NOT embed capability; they *declare* the Expert ids they compose
(``AgentDefinition.experts``). The runtime resolves those ids against this registry, so a
capability is built once and reused across many Agents — Corti's expert paradigm.

This mirrors ``runtime/registry.py`` (the Agent side): one file holds the contract
(``Expert``) and the resolver (``ExpertRegistry``).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .coding_expert import CodingExpert
from .grouping_expert import GroupingExpert


@runtime_checkable
class Expert(Protocol):
    """The contract every Expert satisfies: a stable id Agents compose it by."""

    id: str


class ExpertRegistry:
    def __init__(self) -> None:
        self._experts: dict[str, Expert] = {}

    def register(self, expert: Expert) -> None:
        self._experts[expert.id] = expert

    def get(self, expert_id: str) -> Expert | None:
        return self._experts.get(expert_id)

    def list(self) -> list[Expert]:
        return list(self._experts.values())


def default_expert_registry() -> ExpertRegistry:
    reg = ExpertRegistry()
    reg.register(CodingExpert())
    reg.register(GroupingExpert())
    return reg
