"""ProviderRegistry — process-wide registry of ``AgentBackendProvider``.

Phase 4-A Task 2 (2026-07-07): resolves the right provider for an
agent by reading ``backend_provider`` from the agent pack.

Design (per ``ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md``
Item 6):

  - ``register(provider)`` adds a provider; duplicate ``provider_id``
    raises ``ValueError`` (caller's job to handle).
  - ``get(provider_id)`` returns the provider or raises
    ``ProviderNotRegisteredError`` with an actionable message.
  - ``list()`` returns ``[provider_id, ...]`` — cheap, no instantiation.
  - ``list_by_type(backend_type)`` filters by ``backend_type``.
  - ``health(provider_id)`` calls ``provider.health()`` and wraps
    exceptions into a ``ProviderHealth(state='down')`` envelope.
  - ``resolve_from_agent_pack(agent_pack)`` is the main entry point
    used by ``AgentRunner`` / ``InboundHandler``.

Initialization is LAZY — the registry starts empty and is populated
on first ``resolve_from_agent_pack()`` call via
``_ensure_builtin_providers_registered()``. This means importing this
module costs nothing; the cost is paid only when an agent actually
runs (per Task 2 requirement #5: "registry 初始化不能影响当前启动速度").
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, TYPE_CHECKING

from .contracts import (
    AgentBackendProvider,
    BackendType,
    ProviderCapability,
    ProviderHealth,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Module-level gateway lookup (Phase 4-B Step 3) ───────────────────


_GATEWAY_LOOKUP: Callable[[], Any] | None = None
_GATEWAY_LOOKUP_LOCK = threading.Lock()


def set_gateway_lookup(fn: Callable[[], Any] | None) -> None:
    """Register a callable that returns the process-wide ``LLMGateway``.

    Called once at app startup (``app/main.py`` lifespan) with
    ``lambda: app.state.platform_gateway``. The lookup is lazy —
    ``PureLLMProvider`` calls it on first ``invoke()`` so startup
    speed is unaffected (Task 2 requirement #5 still honored).

    Passing ``None`` clears the lookup (test hook).
    """
    global _GATEWAY_LOOKUP
    with _GATEWAY_LOOKUP_LOCK:
        _GATEWAY_LOOKUP = fn


def get_gateway() -> Any | None:
    """Return the process-wide ``LLMGateway``, or ``None`` if not set.

    Called by ``PureLLMProvider._resolve_client()`` on first invoke.
    Returns ``None`` when:
      - ``set_gateway_lookup`` was never called (e.g., unit tests
        that don't boot the full app)
      - The lookup callable itself returns ``None`` (gateway not yet
        initialized in ``app.state``)
    """
    if _GATEWAY_LOOKUP is None:
        return None
    try:
        return _GATEWAY_LOOKUP()
    except Exception as e:
        logger.warning("gateway lookup raised: %s", e)
        return None


DEFAULT_FALLBACK_PROVIDER_ID = "icoder.rule-engine.v1"
"""Used when an agent pack omits ``backend_provider`` (legacy v1.0 packs).

This preserves backward compat with the 16 existing official agent
packs (per Task 3 requirement #2: "没有 backend_provider 时使用 legacy path").
"""


class ProviderNotRegisteredError(RuntimeError):
    """Raised when ``ProviderRegistry.get(provider_id)`` can't find the provider.

    The message is actionable — names the missing provider_id and
    lists the registered ones so the caller can fix the agent pack.
    """

    def __init__(self, provider_id: str, registered: list[str]) -> None:
        super().__init__(
            f"backend_provider {provider_id!r} not registered. "
            f"Registered providers: {sorted(registered) or '(none)'}. "
            f"Did you forget to register it in ProviderRegistry, or is "
            f"the agent_pack.json backend_provider field mistyped?"
        )
        self.provider_id = provider_id
        self.registered = list(registered)


class ProviderRegistry:
    """Process-wide provider registry. Thread-safe via a single RLock.

    The registry is a dict ``provider_id -> provider instance``. The
    same provider_id registered twice raises ``ValueError`` — callers
    must unregister first.
    """

    def __init__(self, *, auto_register_builtins: bool = True) -> None:
        self._providers: dict[str, AgentBackendProvider] = {}
        self._lock = threading.RLock()
        self._initialized_builtins = False
        self._auto_register_builtins = auto_register_builtins

    # ── Registration ──────────────────────────────────────────────

    def register(self, provider: AgentBackendProvider) -> None:
        """Add a provider. Raises ``ValueError`` on duplicate provider_id."""
        pid = getattr(provider, "provider_id", "")
        if not pid:
            raise ValueError(
                f"provider {provider!r} has no provider_id — cannot register"
            )
        with self._lock:
            if pid in self._providers:
                raise ValueError(
                    f"provider_id {pid!r} already registered "
                    f"(existing={self._providers[pid]!r}). "
                    f"Call unregister({pid!r}) first."
                )
            self._providers[pid] = provider
            logger.debug("provider registered: %s (%s)", pid,
                         getattr(provider, "backend_type", "unknown"))

    def unregister(self, provider_id: str) -> AgentBackendProvider | None:
        """Remove a provider. Returns the removed instance, or None if absent."""
        with self._lock:
            return self._providers.pop(provider_id, None)

    # ── Lookup ────────────────────────────────────────────────────

    def get(self, provider_id: str) -> AgentBackendProvider:
        """Return the provider, or raise ``ProviderNotRegisteredError``."""
        self._ensure_builtins()
        with self._lock:
            provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderNotRegisteredError(
                provider_id, list(self._providers.keys()),
            )
        return provider

    def get_or_default(self, provider_id: str | None) -> AgentBackendProvider:
        """Like ``get`` but falls back to ``DEFAULT_FALLBACK_PROVIDER_ID``
        when ``provider_id`` is None or empty (legacy v1.0 packs).
        """
        if not provider_id:
            self._ensure_builtins()
            with self._lock:
                return self._providers[DEFAULT_FALLBACK_PROVIDER_ID]
        return self.get(provider_id)

    def list(self) -> list[str]:
        """List all registered provider_ids."""
        self._ensure_builtins()
        with self._lock:
            return sorted(self._providers.keys())

    def list_by_type(self, backend_type: BackendType | str) -> list[AgentBackendProvider]:
        """List providers matching ``backend_type``."""
        self._ensure_builtins()
        with self._lock:
            return [
                p for p in self._providers.values()
                if getattr(p, "backend_type", "") == backend_type
            ]

    def list_capabilities(self) -> list[ProviderCapability]:
        """Return ``ProviderCapability`` for each registered provider.

        Used by ``GET /api/v1/agent-runtime/providers/health`` (Phase 4-B)
        and by ``icoder pack validate`` to check tool_scope validity.
        """
        self._ensure_builtins()
        with self._lock:
            providers = list(self._providers.values())
        out: list[ProviderCapability] = []
        for p in providers:
            try:
                cap = p.capabilities()  # type: ignore[attr-defined]
                if isinstance(cap, ProviderCapability):
                    out.append(cap)
            except Exception as e:  # defensive — never break listing
                logger.warning("provider %s capabilities() raised: %s",
                               getattr(p, "provider_id", "?"), e)
        return out

    # ── Health ────────────────────────────────────────────────────

    async def health(self, provider_id: str) -> ProviderHealth:
        """Health probe for one provider. Returns ``state='down'`` on error."""
        try:
            provider = self.get(provider_id)
        except ProviderNotRegisteredError:
            return ProviderHealth(
                state="down",
                details={"error": f"not registered: {provider_id}"},
            )
        try:
            result = await provider.health()  # type: ignore[attr-defined]
            if isinstance(result, ProviderHealth):
                return result
            # Defensive: provider returned something else — wrap it.
            return ProviderHealth(
                state="degraded",
                details={"raw": str(result)[:200]},
            )
        except NotImplementedError:
            return ProviderHealth(state="ok", details={"note": "health() not implemented"})
        except Exception as e:
            logger.warning("provider %s health() raised: %s", provider_id, e)
            return ProviderHealth(
                state="down",
                details={"error": f"{type(e).__name__}: {str(e)[:200]}"},
            )

    async def health_all(self) -> dict[str, ProviderHealth]:
        """Health for every registered provider. Never raises."""
        self._ensure_builtins()
        with self._lock:
            ids = list(self._providers.keys())
        results: dict[str, ProviderHealth] = {}
        for pid in ids:
            results[pid] = await self.health(pid)
        return results

    # ── Agent-pack resolution ─────────────────────────────────────

    def resolve_from_agent_pack(
        self, agent_pack: dict[str, Any],
    ) -> AgentBackendProvider:
        """The main entry point used by ``AgentRunner`` / ``InboundHandler``.

        Reads ``backend_provider`` from the agent pack (top-level or
        nested under ``agent``) and returns the registered provider.

        If ``backend_provider`` is absent, returns the default fallback
        (``icoder.rule-engine.v1``) — preserves backward compat with
        v1.0 packs that don't declare a backend.
        """
        provider_id = _extract_backend_provider(agent_pack)
        return self.get_or_default(provider_id)

    def get_backend_config(
        self, agent_pack: dict[str, Any],
    ) -> dict[str, Any]:
        """Return ``backend_config`` from the agent pack (or ``{}``)."""
        return _extract_backend_config(agent_pack)

    # ── Lazy builtin registration ─────────────────────────────────

    def _ensure_builtins(self) -> None:
        """Lazy-register builtin providers on first lookup.

        Idempotent — sets ``_initialized_builtins`` so subsequent calls
        are no-ops. This is what makes the registry not affect startup
        speed (Task 2 requirement #5).

        When ``auto_register_builtins=False`` (test mode), this is a
        no-op — the registry stays empty until the caller explicitly
        registers providers.
        """
        if self._initialized_builtins:
            return
        if not self._auto_register_builtins:
            self._initialized_builtins = True
            return
        with self._lock:
            if self._initialized_builtins:
                return
            self._initialized_builtins = True
            try:
                _register_builtin_providers(self)
            except Exception as e:
                # Defensive — never break the registry on lazy init failure.
                logger.error("builtin provider registration failed: %s", e)


# ── Module-level default registry ──────────────────────────────────────


_DEFAULT_REGISTRY: ProviderRegistry | None = None
_DEFAULT_REGISTRY_LOCK = threading.Lock()


def get_default_registry() -> ProviderRegistry:
    """Return the process-wide default registry.

    Tests can call ``reset_default_registry()`` to start fresh.
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _DEFAULT_REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = ProviderRegistry()
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """Reset the default registry. Test hook — never call in production."""
    global _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        _DEFAULT_REGISTRY = None


# ── Agent-pack field extractors ────────────────────────────────────────


def _extract_backend_provider(agent_pack: dict[str, Any]) -> str:
    """Pull ``backend_provider`` from the agent pack.

    Supports both top-level and nested-under-agent shapes, so packs
    can be either:
      ``{"backend_provider": "icoder.rule-engine.v1", ...}``
      or
      ``{"agent": {"backend_provider": "icoder.rule-engine.v1", ...}, ...}``
    """
    if not isinstance(agent_pack, dict):
        return ""
    top = agent_pack.get("backend_provider")
    if isinstance(top, str) and top:
        return top
    agent_node = agent_pack.get("agent")
    if isinstance(agent_node, dict):
        nested = agent_node.get("backend_provider")
        if isinstance(nested, str) and nested:
            return nested
    return ""


def _extract_backend_config(agent_pack: dict[str, Any]) -> dict[str, Any]:
    """Pull ``backend_config`` from the agent pack (top-level or nested)."""
    if not isinstance(agent_pack, dict):
        return {}
    top = agent_pack.get("backend_config")
    if isinstance(top, dict):
        return top
    agent_node = agent_pack.get("agent")
    if isinstance(agent_node, dict):
        nested = agent_node.get("backend_config")
        if isinstance(nested, dict):
            return nested
    return {}


def _register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register the 3 Phase 4-A builtin providers.

    Phase 4-A only ships: RuleEngineProvider, PureLLMProvider (skeleton),
    LLMWithToolsProvider (skeleton). The 5 meta-providers (ensemble,
    cascade, hybrid, cached, external_a2a) ship in Phase 4-D.
    """
    # Import locally so module import doesn't pay for provider imports.
    from .rule_engine_provider import RuleEngineProvider
    from .pure_llm_provider import PureLLMProvider
    from .llm_with_tools_provider import LLMWithToolsProvider

    candidates: list[AgentBackendProvider] = []

    # RuleEngineProvider — always succeeds (no external deps).
    try:
        candidates.append(RuleEngineProvider())
    except Exception as e:  # defensive
        logger.error("RuleEngineProvider init failed: %s", e)

    # PureLLMProvider skeleton — init may need an LLM gateway; on
    # failure, skip (the skeleton is testable, not production-wired).
    try:
        candidates.append(PureLLMProvider())
    except Exception as e:
        logger.debug("PureLLMProvider init skipped: %s", e)

    # LLMWithToolsProvider skeleton.
    try:
        candidates.append(LLMWithToolsProvider())
    except Exception as e:
        logger.debug("LLMWithToolsProvider init skipped: %s", e)

    for provider in candidates:
        try:
            registry.register(provider)
        except ValueError as e:
            # Already registered — fine for the default registry.
            logger.debug("provider already registered: %s", e)


__all__ = [
    "ProviderRegistry",
    "ProviderNotRegisteredError",
    "DEFAULT_FALLBACK_PROVIDER_ID",
    "get_default_registry",
    "reset_default_registry",
    "set_gateway_lookup",
    "get_gateway",
]
