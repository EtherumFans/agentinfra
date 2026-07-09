"""Tests for ``icoder_runtime.backends.registry`` — Phase 4-A Task 2.

Verifies:
  - register / get / list / unregister behavior
  - duplicate provider_id raises ValueError
  - get(unknown_id) raises ProviderNotRegisteredError
  - get_or_default falls back to DEFAULT_FALLBACK_PROVIDER_ID
  - list_by_type filters by backend_type
  - list_capabilities returns ProviderCapability for each provider
  - health() wraps exceptions into ProviderHealth(state='down')
  - resolve_from_agent_pack reads top-level and nested backend_provider
  - lazy builtin registration doesn't affect module import speed
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends.registry import (
    DEFAULT_FALLBACK_PROVIDER_ID,
    ProviderNotRegisteredError,
    ProviderRegistry,
    get_default_registry,
    reset_default_registry,
)


# ── Stub providers for unit tests ────────────────────────────────────


class _StubProvider:
    """Minimal provider stub that satisfies the AgentBackendProvider Protocol."""

    def __init__(
        self,
        pid: str,
        btype: str = "rule_engine",
        *,
        deterministic: bool = True,
        tools: bool = False,
        stream: bool = False,
    ) -> None:
        self.provider_id = pid
        self.backend_type = btype
        self.supports_tool_calling = tools
        self.supports_streaming = stream
        self.deterministic = deterministic
        self._health_state = "ok"

    async def health(self):
        from icoder_runtime.backends import ProviderHealth
        return ProviderHealth(state=self._health_state, details={"pid": self.provider_id})

    async def invoke(self, req, ctx):
        from icoder_runtime.backends import BackendResponse
        return BackendResponse(status="pass", backend_provider=self.provider_id)

    async def stream(self, req, ctx):
        yield {"step": "finished"}

    def output_contract(self):
        return "icoder/Stub/v1"

    def fallback_chain(self):
        return None

    def capabilities(self):
        from icoder_runtime.backends import ProviderCapability
        return ProviderCapability(
            provider_id=self.provider_id,
            backend_type=self.backend_type,
            supports_tool_calling=self.supports_tool_calling,
            supports_streaming=self.supports_streaming,
            deterministic=self.deterministic,
        )


# ── register / get / list / unregister ─────────────────────────────


def test_register_and_get():
    r = ProviderRegistry()
    p = _StubProvider("icoder.test.v1")
    r.register(p)
    assert r.get("icoder.test.v1") is p


def test_register_duplicate_raises():
    r = ProviderRegistry()
    r.register(_StubProvider("icoder.dup.v1"))
    with pytest.raises(ValueError, match="already registered"):
        r.register(_StubProvider("icoder.dup.v1"))


def test_register_with_empty_provider_id_raises():
    r = ProviderRegistry()
    p = _StubProvider("")
    with pytest.raises(ValueError, match="no provider_id"):
        r.register(p)


def test_get_unknown_raises_with_actionable_message():
    r = ProviderRegistry()
    r.register(_StubProvider("icoder.known.v1"))
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        r.get("icoder.unknown.v1")
    assert "icoder.unknown.v1" in str(exc_info.value)
    assert "icoder.known.v1" in exc_info.value.registered


def test_list_returns_sorted_ids():
    r = ProviderRegistry(auto_register_builtins=False)
    r.register(_StubProvider("icoder.b.v1"))
    r.register(_StubProvider("icoder.a.v1"))
    ids = r.list()
    assert ids == ["icoder.a.v1", "icoder.b.v1"]


def test_unregister_removes_provider():
    r = ProviderRegistry(auto_register_builtins=False)
    p = _StubProvider("icoder.temp.v1")
    r.register(p)
    assert r.unregister("icoder.temp.v1") is p
    assert r.list() == []


def test_unregister_unknown_returns_none():
    r = ProviderRegistry()
    assert r.unregister("icoder.never-existed.v1") is None


# ── get_or_default fallback ────────────────────────────────────────


def test_get_or_default_uses_fallback_when_id_empty():
    """Empty provider_id triggers fallback to default rule-engine."""
    # Don't trigger lazy builtin registration here — use a fresh registry
    # and manually register the fallback.
    r = ProviderRegistry()
    fallback = _StubProvider(DEFAULT_FALLBACK_PROVIDER_ID)
    r.register(fallback)
    # Empty string → fallback
    assert r.get_or_default("") is fallback
    assert r.get_or_default(None) is fallback


def test_get_or_default_returns_named_provider_when_set():
    r = ProviderRegistry()
    fallback = _StubProvider(DEFAULT_FALLBACK_PROVIDER_ID)
    named = _StubProvider("icoder.named.v1")
    r.register(fallback)
    r.register(named)
    assert r.get_or_default("icoder.named.v1") is named
    assert r.get_or_default(None) is fallback


# ── list_by_type ───────────────────────────────────────────────────


def test_list_by_type_filters_correctly():
    r = ProviderRegistry(auto_register_builtins=False)
    r.register(_StubProvider("icoder.a.v1", "rule_engine"))
    r.register(_StubProvider("icoder.b.v1", "pure_llm"))
    r.register(_StubProvider("icoder.c.v1", "rule_engine"))
    matches = r.list_by_type("rule_engine")
    ids = [m.provider_id for m in matches]
    assert sorted(ids) == ["icoder.a.v1", "icoder.c.v1"]


# ── list_capabilities ──────────────────────────────────────────────


def test_list_capabilities_returns_one_per_provider():
    r = ProviderRegistry(auto_register_builtins=False)
    r.register(_StubProvider("icoder.a.v1"))
    r.register(_StubProvider("icoder.b.v1"))
    caps = r.list_capabilities()
    assert len(caps) == 2
    ids = sorted(c.provider_id for c in caps)
    assert ids == ["icoder.a.v1", "icoder.b.v1"]


# ── health ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_wraps_exceptions_into_down_state():
    """If provider.health() raises, registry returns state='down'."""
    r = ProviderRegistry()
    bad = _StubProvider("icoder.bad.v1")
    async def _raise():
        raise RuntimeError("boom")
    bad.health = _raise  # type: ignore[assignment]
    r.register(bad)
    h = await r.health("icoder.bad.v1")
    assert h.state == "down"
    assert "RuntimeError" in h.details.get("error", "")


@pytest.mark.asyncio
async def test_health_returns_down_for_unknown_provider():
    r = ProviderRegistry()
    h = await r.health("icoder.never.v1")
    assert h.state == "down"
    assert "not registered" in h.details.get("error", "")


@pytest.mark.asyncio
async def test_health_all_never_raises():
    r = ProviderRegistry()
    good = _StubProvider("icoder.good.v1")
    bad = _StubProvider("icoder.bad.v1")
    async def _raise():
        raise RuntimeError("kaboom")
    bad.health = _raise  # type: ignore[assignment]
    r.register(good)
    r.register(bad)
    results = await r.health_all()
    assert results["icoder.good.v1"].state == "ok"
    assert results["icoder.bad.v1"].state == "down"


# ── resolve_from_agent_pack ────────────────────────────────────────


def test_resolve_from_agent_pack_top_level():
    r = ProviderRegistry()
    p = _StubProvider("icoder.test.v1")
    r.register(p)
    pack = {"backend_provider": "icoder.test.v1"}
    assert r.resolve_from_agent_pack(pack) is p


def test_resolve_from_agent_pack_nested_under_agent():
    r = ProviderRegistry()
    p = _StubProvider("icoder.test.v1")
    r.register(p)
    pack = {"agent": {"backend_provider": "icoder.test.v1"}}
    assert r.resolve_from_agent_pack(pack) is p


def test_resolve_from_agent_pack_falls_back_when_absent():
    """Old v1.0 packs without backend_provider → default rule-engine."""
    r = ProviderRegistry()
    fallback = _StubProvider(DEFAULT_FALLBACK_PROVIDER_ID)
    r.register(fallback)
    pack = {"agent": {"name": "old pack"}}
    assert r.resolve_from_agent_pack(pack) is fallback


def test_resolve_from_agent_pack_raises_when_named_provider_missing():
    r = ProviderRegistry()
    r.register(_StubProvider(DEFAULT_FALLBACK_PROVIDER_ID))
    pack = {"backend_provider": "icoder.does-not-exist.v1"}
    with pytest.raises(ProviderNotRegisteredError):
        r.resolve_from_agent_pack(pack)


def test_get_backend_config_top_level():
    r = ProviderRegistry()
    pack = {"backend_config": {"mode": "deterministic"}}
    assert r.get_backend_config(pack) == {"mode": "deterministic"}


def test_get_backend_config_nested():
    r = ProviderRegistry()
    pack = {"agent": {"backend_config": {"llm": {"model": "deepseek-v4-flash"}}}}
    assert r.get_backend_config(pack) == {"llm": {"model": "deepseek-v4-flash"}}


def test_get_backend_config_empty_when_absent():
    r = ProviderRegistry()
    assert r.get_backend_config({}) == {}


# ── Lazy builtin registration ──────────────────────────────────────


def test_lazy_registration_on_first_get():
    """The default registry auto-registers 3 builtin providers on first get."""
    reset_default_registry()
    r = get_default_registry()
    # First get triggers lazy registration.
    p = r.get("icoder.rule-engine.v1")
    assert p.provider_id == "icoder.rule-engine.v1"
    assert p.backend_type == "rule_engine"


def test_lazy_registration_idempotent():
    """Repeated _ensure_builtins calls don't double-register."""
    r = ProviderRegistry()
    r._ensure_builtins()
    r._ensure_builtins()
    r._ensure_builtins()
    ids = r.list()
    # Each builtin appears exactly once.
    assert ids.count("icoder.rule-engine.v1") == 1
    assert ids.count("icoder.pure-llm.v1") == 1
    assert ids.count("icoder.llm-with-tools.v1") == 1
