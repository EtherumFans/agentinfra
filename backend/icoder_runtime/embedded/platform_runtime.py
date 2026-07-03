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
from ..agent_pack import import_pack

# Phase 2.1-A (2026-07-02): legacy AgentRunner stub dependency cut.
# PlatformRuntime no longer holds a `_runner` slot and no longer imports
# AgentRunner. Execution (`run_agent`) now raises NotImplementedError with a
# redirect to the A2A mainline (`app.icoder.agent_runtime.orchestrator.
# InboundHandler`). Registry/install/status paths are unaffected — they
# never depended on `_runner` for anything beyond no-op register_* calls.

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
        self._started = False
        self._started_at: str = ""
        self._data_policy = data_policy

    # ── Lifecycle ──

    async def start(self):
        """Initialize the runtime: load registry.

        Phase 2.1-A: no longer creates an AgentRunner — execution is delegated
        to the A2A mainline (`app.icoder.agent_runtime.orchestrator.
        InboundHandler`), exposed via `mount_a2a` in `app/main.py`."""
        self._started = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"PlatformRuntime started (mode={self._config.execution_mode}): "
            f"{self._registry.count} agent(s) in registry. "
            f"Execution path: A2A InboundHandler (legacy _runner slot removed)."
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

        # Phase 2.1-A: no longer register experts/tools with a `_runner` —
        # the A2A InboundHandler resolves experts/tools at call time via
        # the registry + MCP tools/list. The previous register_* calls were
        # no-ops on the stub anyway.

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

        Phase 2.1-A (2026-07-02): DEPRECATED for execution. The legacy
        ``_runner.run()`` path is removed; this method now raises
        ``NotImplementedError`` with a redirect to the A2A mainline.

        Migration path: use the A2A endpoints exposed by
        ``app.icoder.agent_runtime.a2a.mount_a2a`` (mounted in
        ``app/main.py`` lifespan) — they route through the new
        ``InboundHandler`` orchestrator (Planner → Delegator → Aggregator)
        which is the only supported execution path.

        This method is retained only so that callers that still call
        ``rt.run_agent(...)`` get a clear redirect message instead of an
        ``AttributeError`` on the missing ``_runner`` slot.

        Raises:
            AgentNotFoundError: if agent_id is not installed
            NotImplementedError: always — execution moved to A2A mainline
        """
        record = self._registry.get(agent_id)
        if not record:
            raise AgentNotFoundError(f"Agent not installed: {agent_id}")
        raise NotImplementedError(
            "PlatformRuntime.run_agent removed in Phase 2.1-A. "
            "Execution moved to the A2A mainline "
            "(`app.icoder.agent_runtime.orchestrator.InboundHandler`, mounted "
            "via `mount_a2a` in app/main.py). Use the A2A endpoints "
            "(e.g. POST /a2a/v1/...) instead of /api/runtime/agents/{ref}/run."
        )
