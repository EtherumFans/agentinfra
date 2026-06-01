"""Core types for iCoDer Runtime — DB-independent dataclasses."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ToolTier(int, Enum):
    DETERMINISTIC = 1
    LLM_REASONING = 2


class PermissionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_HUMAN = "require_human"


@dataclass
class ExpertDefinition:
    """An expert Agent can call. DB-independent."""
    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    category: str = "general"
    capabilities: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


@dataclass
class AgentDefinition:
    """An Agent that orchestrates Experts. DB-independent."""
    id: str = ""
    name: str = "Untitled Agent"
    description: str = ""
    system_prompt: str = ""
    icon: str = "Bot"
    category: str = "general"
    expert_ids: list[str] = field(default_factory=list)
    default_expert_id: str = ""
    config: dict = field(default_factory=dict)
    is_prebuilt: bool = False
    version: str = "1.0.0"
    status: str = "draft"


@dataclass
class ToolDefinition:
    """Immutable metadata for a tool capability."""
    id: str
    name: str
    description: str
    tier: ToolTier
    category: str
    icon: str = "Wrench"
    requires: list[str] = field(default_factory=list)
    guarantees: dict[str, str] = field(default_factory=dict)
    executor: Optional[callable] = None
    input_schema: Optional[dict] = None
    accuracy_tags: list[str] = field(default_factory=list)
    is_injectable: bool = False
