"""Platform Runtime — the Embedded Runtime that runs inside iCoDer main platform.

This is the DEFAULT runtime form for production and demo.
It wraps Runtime Core and provides install, list, run operations
that the main platform's API layer can call directly.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.errors import (
    AgentNotFoundError,
    InstallError,
    LLMProviderNotConfigured,
    ValidationError,
)
from ..core.llm_gateway import LLMGateway, MockLLMProvider
from ..core.agent_pack_v1 import AgentPackageV1
from ..core.registry import RuntimeAgentRegistry, get_registry, InstalledAgentRecord
from ..core.runtime_config import RuntimeConfig
from ..agent_runner import AgentRunner
from ..agent_pack import import_pack

logger = logging.getLogger(__name__)

# Default storage path
DEFAULT_REGISTRY_DIR = Path(".icoder")


class PlatformRuntime:
    """Embedded Runtime that lives inside the iCoDer main platform.

    Uses RuntimeAgentRegistry for persistent agent storage.
    Supports feature-flagged execution modes: legacy / platform_runtime / shadow.

    Usage:
        config = RuntimeConfig(execution_mode="platform_runtime")
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)

        rt = PlatformRuntime(gateway=gateway, config=config)
        await rt.start()

        result = rt.install_agent(pack_dict)
        agents = rt.list_agents()
        output = await rt.run_agent(agent_id, "病历文本...")
    """

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        config: RuntimeConfig | None = None,
        registry: RuntimeAgentRegistry | None = None,
        storage_dir: str | Path = "",
        data_policy=None,
    ):
        self._gateway = gateway or LLMGateway()
        self._config = config or RuntimeConfig.from_env()
        self._registry = registry or get_registry(
            storage_dir or self._config.registry_dir
        )
        self._runner: AgentRunner | None = None
        self._started = False
        self._started_at: str = ""
        self._data_policy = data_policy

    # ── Lifecycle ──

    async def start(self):
        """Initialize the runtime: create runner, load registry."""
        self._runner = AgentRunner(gateway=self._gateway)
        self._started = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        # Register existing agents' experts/tools with the runner
        for rec in self._registry.list_all():
            for exp_data in rec.experts or []:
                from ..types import ExpertDefinition
                self._runner.register_expert(ExpertDefinition(**exp_data))
        logger.info(
            f"PlatformRuntime started (mode={self._config.execution_mode}): "
            f"{self._registry.count} agent(s) in registry."
        )

    async def stop(self):
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    # ── Config ──

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    # ── Status ──

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "started_at": self._started_at,
            "execution_mode": self._config.execution_mode,
            "review_coding_mode": self._config.review_coding_mode,
            "fallback_to_legacy": self._config.fallback_to_legacy,
            "agents_installed": self._registry.count,
            "providers": self._gateway.list_providers(),
            "default_provider": self._gateway.default_provider,
        }

    # ── Agent Management (delegates to RuntimeAgentRegistry) ──

    def install_agent(self, pack: dict, *, publisher_name: str = "", publisher_email: str = "") -> dict[str, Any]:
        """Install an agent from a .icoder-agent pack dict into the persistent registry.

        Returns: {"agent_id": str, "name": str, "version": str, "status": "installed"}
        """
        # Validate via AgentPackageV1 (legacy v1.1 strict checks). v1.2 packs
        # (reference / expert-stub agent_types, MCP-style tools[].ref) are
        # already validated by BuiltinAgentPackProvider.discover_all() — see
        # docs/specs/AGENT_PACK_SPEC_V1_2.md §1. Skipping the legacy validator
        # here unblocks v1.2 packs that were silently dropped at startup with
        # only a `Failed to register pack` warning.
        if pack.get("format_version", "1.1") == "1.1":
            pkg = AgentPackageV1.from_dict(pack)
            resolved_publisher_name = publisher_name or pkg.publisher_name
            resolved_publisher_email = publisher_email or pkg.publisher_email
        else:
            pkg = None
            resolved_publisher_name = publisher_name or pack.get("publisher_name", "")
            resolved_publisher_email = publisher_email or pack.get("publisher_email", "")

        # Import into domain objects for runner registration
        agent, experts, tools, permissions = import_pack(pack)

        # Install into persistent registry
        record = self._registry.install(
            pack,
            publisher_name=resolved_publisher_name,
            publisher_email=resolved_publisher_email,
        )

        # Register experts and tools with the runner
        if self._runner:
            for e in experts:
                self._runner.register_expert(e)
            for t in tools:
                self._runner.register_tool(t)

        logger.info(f"Agent installed: {record.agent_id}")
        # DB sync is handled in main.py startup (Registry→DB)
        return {"agent_id": record.agent_id, "name": record.name, "version": record.version, "status": "installed"}

    def list_agents(self, agent_type: str = "") -> list[dict[str, Any]]:
        """List all installed agents from the registry."""
        records = self._registry.list_all(agent_type=agent_type)
        return [r.to_summary() for r in records]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get a single installed agent by id from the registry."""
        return self._registry.get(agent_id).to_dict()

    # ── Execution ──

    async def run_agent(
        self,
        agent_id: str,
        user_input: str,
        *,
        permission_policy=None,
        delegated_by: dict | None = None,
    ) -> dict[str, Any]:
        """Run an installed agent against user input.

        delegated_by: {"user_id": "...", "username": "...", "agent_account_id": "..."}
        When provided, the Agent executes on behalf of this user with a delegation JWT.

        Looks up the agent in the persistent RuntimeAgentRegistry.

        Raises:
            AgentNotFoundError: if agent_id is not installed
            LLMProviderNotConfigured: if no LLM provider
        """
        record = self._registry.get(agent_id)
        if not self._runner:
            raise LLMProviderNotConfigured()

        from ..types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
        from ..permissions import PermissionPolicy, ToolPermission

        # Rebuild AgentDefinition from registry record
        agent = AgentDefinition(
            name=record.name,
            version=record.version,
            description=record.description,
            category=record.category,
            icon=record.icon,
            system_prompt=record.system_prompt,
            expert_ids=record.expert_ids or [],
        )

        # Register experts/tools (idempotent). v1.2 packs (Phase D convention) use
        # `expert_id` + carry extra fields (role, tools, model, non_goals,
        # output_contract) that the ExpertDefinition dataclass doesn't know —
        # normalize to the v1.1 dataclass schema before constructing.
        _EXPERT_FIELDS = {"id", "name", "description", "system_prompt",
                         "category", "capabilities", "config"}
        for e in record.experts or []:
            if "expert_id" in e and "id" not in e:
                e_norm = {k: v for k, v in e.items() if k != "expert_id"}
                e_norm["id"] = e["expert_id"]
            else:
                e_norm = e
            e_norm = {k: v for k, v in e_norm.items() if k in _EXPERT_FIELDS}
            self._runner.register_expert(ExpertDefinition(**e_norm))
        for t in record.tools or []:
            if isinstance(t, str):
                self._runner.register_tool(ToolDefinition(id=t, name=t, description=t, tier=ToolTier(1), category="general"))
            else:
                # v1.2 tools use `name` (not `id`) and `type` (not `tier`). Map.
                tool_id = t.get("id") or t.get("name", "")
                tool_name = t.get("name", tool_id)
                t_type = t.get("type")
                if "tier" in t:
                    tier_value = t["tier"]
                elif t_type in ("mcp", "function", "builtin"):
                    tier_value = 1
                elif t_type == "guard":
                    tier_value = 2
                else:
                    tier_value = 2
                self._runner.register_tool(ToolDefinition(
                    id=tool_id, name=tool_name, description=t.get("description", ""),
                    tier=ToolTier(tier_value),
                    category=t.get("category", "general"),
                    requires=t.get("requires", []), guarantees=t.get("guarantees", {}),
                    input_schema={"type": "object", "properties": t.get("params", {})} if t.get("params") else None,
                ))

        return await self._runner.run(
            agent, user_input,
            permission_policy=permission_policy,
            data_policy=self._data_policy,
            delegated_by=delegated_by,
        )
