"""Tool Registry — ToolDefinition + ToolRegistry for contract-enforced tool calling.

Each tool is a self-contained capability with:
- Contract metadata: preconditions (requires) and postconditions (guarantees)
- Tier classification: 1 = deterministic core, 2 = LLM-powered reasoning
- Executor function: async callable that does the actual work
"""

import logging
from dataclasses import dataclass, field
from collections.abc import Callable, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class ToolTier(int, Enum):
    DETERMINISTIC = 1   # Zero-LLM: code_dict, evidence_ranker, calibration, guardrails
    LLM_REASONING = 2   # LLM-powered: extraction, code assignment, report generation


@dataclass
class ToolDefinition:
    """Immutable metadata for a tool capability.

    Each tool is a Hoare-style contract {P} t {Q}:
    - requires (P): what must be true before calling
    - guarantees (Q): what the tool promises in its output
    """

    id: str
    name: str
    description: str
    tier: ToolTier
    category: str  # "extraction" | "coding" | "verification" | "analysis" | "report" | "safety"
    icon: str = "Wrench"

    # Contract
    requires: list[str] = field(default_factory=list)
    guarantees: dict[str, str] = field(default_factory=dict)

    # Execution
    executor: Callable[..., Awaitable[dict]] | None = None
    input_schema: dict | None = None

    # Metadata
    accuracy_tags: list[str] = field(default_factory=list)
    is_injectable: bool = False  # Can be auto-injected by harness for accuracy guarantees

    def __hash__(self) -> int:
        return hash(self.id)


class ToolRegistry:
    """Global registry of all available tools.

    Provides discovery (list by tier/category/tag) and execution
    (resolve + call with parameter validation).
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.id in self._tools:
            logger.warning(f"Tool '{tool.id}' already registered, overwriting")
        self._tools[tool.id] = tool
        logger.info(f"Registered tool: {tool.id} (tier={tool.tier}, category={tool.category})")

    def get(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def list_all(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_by_tier(self, tier: ToolTier) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.tier == tier]

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.category == category]

    def list_by_tag(self, tag: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if tag in t.accuracy_tags]

    def get_categories(self) -> dict[str, list[ToolDefinition]]:
        cats: dict[str, list[ToolDefinition]] = {}
        for t in self._tools.values():
            cats.setdefault(t.category, []).append(t)
        return cats

    def get_injectable_by_tag(self, tag: str) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.is_injectable and tag in t.accuracy_tags]

    def resolve_dependencies(self, tool_ids: list[str]) -> list[str]:
        """Resolve all Tier 1 dependency tools for a given set of tool IDs.

        Walks the requires chain: if a selected tool needs X, and X is Tier 1,
        X gets auto-injected. Returns the complete ordered list (deps first).
        """
        resolved: list[str] = []
        seen: set[str] = set()

        def _resolve(tid: str):
            if tid in seen:
                return
            tool = self._tools.get(tid)
            if not tool:
                return
            seen.add(tid)

            # Resolve dependencies first
            for dep_id in tool.requires:
                dep = self._tools.get(dep_id)
                if dep and dep.tier == ToolTier.DETERMINISTIC:
                    _resolve(dep_id)

            resolved.append(tid)

        for tid in tool_ids:
            _resolve(tid)

        return resolved

    async def execute(self, tool_id: str, params: dict) -> dict:
        """Execute a tool by ID with the given parameters."""
        tool = self._tools.get(tool_id)
        if not tool:
            raise ValueError(f"Tool '{tool_id}' not found in registry")
        if not tool.executor:
            raise ValueError(f"Tool '{tool_id}' has no executor")
        return await tool.executor(**params)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._tools


# Global singleton
tool_registry = ToolRegistry()
