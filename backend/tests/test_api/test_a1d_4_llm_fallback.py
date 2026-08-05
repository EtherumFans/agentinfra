"""A1D.4 — A1C-B-007 LLM fallback provider + automatic failover.

Predecessor state (Phase A1C.9): ``DeepSeekProvider`` returns a
``degraded=True`` mock response on every error path (no API key,
circuit open, 429/503, 4xx, network error). ``LLMGateway`` has no
failover — the caller gets the degraded response. Charter §4 PDF asks
for ≥1 fallback provider (Azure OpenAI / Qwen / Moonshot) so the
runtime keeps serving when DeepSeek is unhealthy.

A1D.4 closes the gap by:
  - ``LLMGateway.register_fallback(provider)`` — register a fallback
    provider. Auto-failover: when the primary returns a response with
    ``degraded=True``, the gateway calls the fallback next.
  - ``fallback_provider.py`` — constructor helpers for ≥1 real
    fallback (Azure-OpenAI-compatible via ``OpenAICompatibleProvider``
    subclass + Qwen/Moonshot aliases). Real API keys deferred to Pilot.
  - ``FALLBACK_FAILOVER_TEST_RESULTS.json`` — verification artifact.

The fallback mechanism is provider-agnostic — any ``BaseLLMProvider``
subclass can serve as fallback. Pilot env wires real keys.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 LLMGateway.register_fallback — API surface
# ─────────────────────────────────────────────────────────────────────


def test_llm_gateway_register_fallback_returns_self():
    """register_fallback() returns the gateway for chaining."""
    from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider
    gw = LLMGateway()
    gw.register(MockLLMProvider(), default=True)
    fb = MockLLMProvider(name="fb")
    ret = gw.register_fallback(fb)
    assert ret is gw


def test_llm_gateway_register_fallback_accepts_multiple_providers():
    """Multiple fallbacks can be registered; they form an ordered chain."""
    from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider
    gw = LLMGateway()
    gw.register(MockLLMProvider(), default=True)
    gw.register_fallback(MockLLMProvider(name="fb1"))
    gw.register_fallback(MockLLMProvider(name="fb2"))
    assert len(gw.fallback_chain) == 2
    assert gw.fallback_chain[0].name == "fb1"
    assert gw.fallback_chain[1].name == "fb2"


# ─────────────────────────────────────────────────────────────────────
# §2 Auto-failover — primary degraded → fallback called
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gateway_generate_falls_back_when_primary_degraded():
    """When the primary returns degraded=True, the gateway calls the fallback."""
    from icoder_runtime.core.llm_gateway import (
        LLMGateway, BaseLLMProvider, _mock_fallback_response,
    )

    class _DegradedPrimary(BaseLLMProvider):
        name = "primary"
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            return _mock_fallback_response("no_api_key")
        def health_check(self): return {"provider": "primary", "status": "degraded"}

    class _HealthyFallback(BaseLLMProvider):
        name = "fallback"
        def __init__(self): self.called = False
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            self.called = True
            return {
                "content": "fallback answer",
                "provider": "fallback",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "degraded": False,
            }
        def health_check(self): return {"provider": "fallback", "status": "healthy"}

    gw = LLMGateway()
    fb = _HealthyFallback()
    gw.register(_DegradedPrimary(), default=True)
    gw.register_fallback(fb)

    result = await gw.generate(messages=[{"role": "user", "content": "hi"}])

    assert fb.called is True
    assert result["provider"] == "fallback"
    assert result.get("degraded") is not True
    # Failover provenance is recorded for audit
    assert result.get("fallback_from") == "primary"
    assert result.get("fallback_reason") == "no_api_key"


@pytest.mark.asyncio
async def test_gateway_generate_skips_fallback_when_primary_healthy():
    """When the primary returns a healthy response, fallback is NOT called."""
    from icoder_runtime.core.llm_gateway import LLMGateway, BaseLLMProvider

    class _HealthyPrimary(BaseLLMProvider):
        name = "primary"
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            return {
                "content": "primary answer",
                "provider": "primary",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "degraded": False,
            }
        def health_check(self): return {"provider": "primary", "status": "healthy"}

    class _SpyFallback(BaseLLMProvider):
        name = "fallback"
        def __init__(self): self.called = False
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            self.called = True
            return {"content": "fb", "provider": "fallback", "degraded": False}
        def health_check(self): return {"provider": "fallback", "status": "healthy"}

    gw = LLMGateway()
    fb = _SpyFallback()
    gw.register(_HealthyPrimary(), default=True)
    gw.register_fallback(fb)

    result = await gw.generate(messages=[{"role": "user", "content": "hi"}])

    assert fb.called is False
    assert result["provider"] == "primary"


@pytest.mark.asyncio
async def test_gateway_generate_falls_through_chain_to_second_fallback():
    """Multiple fallbacks: if 1st fallback also degrades, try the 2nd."""
    from icoder_runtime.core.llm_gateway import (
        LLMGateway, BaseLLMProvider, _mock_fallback_response,
    )

    class _DegradedPrimary(BaseLLMProvider):
        name = "primary"
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            return _mock_fallback_response("circuit_open")
        def health_check(self): return {"status": "degraded"}

    class _DegradedFallback1(BaseLLMProvider):
        name = "fb1"
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            return _mock_fallback_response("no_api_key")
        def health_check(self): return {"status": "degraded"}

    class _HealthyFallback2(BaseLLMProvider):
        name = "fb2"
        def __init__(self): self.called = False
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            self.called = True
            return {
                "content": "fb2 answer",
                "provider": "fb2",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "degraded": False,
            }
        def health_check(self): return {"status": "healthy"}

    gw = LLMGateway()
    fb2 = _HealthyFallback2()
    gw.register(_DegradedPrimary(), default=True)
    gw.register_fallback(_DegradedFallback1())
    gw.register_fallback(fb2)

    result = await gw.generate(messages=[{"role": "user", "content": "hi"}])

    assert fb2.called is True
    assert result["provider"] == "fb2"
    assert result.get("fallback_from") == "primary"


@pytest.mark.asyncio
async def test_gateway_generate_all_degraded_returns_last_degraded_with_provenance():
    """All providers degraded → return last degraded response + failover trail."""
    from icoder_runtime.core.llm_gateway import (
        LLMGateway, BaseLLMProvider, _mock_fallback_response,
    )

    class _Degraded(BaseLLMProvider):
        def __init__(self, name, reason):
            self.name = name
            self._reason = reason
        async def generate(self, *, messages, tools=None, response_schema=None, context=None):
            return _mock_fallback_response(self._reason)
        def health_check(self): return {"status": "degraded"}

    gw = LLMGateway()
    gw.register(_Degraded("primary", "no_api_key"), default=True)
    gw.register_fallback(_Degraded("fb1", "circuit_open"))
    gw.register_fallback(_Degraded("fb2", "provider_network_error"))

    result = await gw.generate(messages=[{"role": "user", "content": "hi"}])

    assert result.get("degraded") is True
    # Failover trail records each provider + its degraded_reason
    trail = result.get("failover_trail", [])
    assert [t["provider"] for t in trail] == ["primary", "fb1", "fb2"]
    assert [t["reason"] for t in trail] == [
        "no_api_key", "circuit_open", "provider_network_error",
    ]


# ─────────────────────────────────────────────────────────────────────
# §3 fallback_provider.py — constructor helpers
# ─────────────────────────────────────────────────────────────────────


def test_fallback_provider_module_exports_factory_functions():
    """fallback_provider.py exposes ≥1 factory for a real fallback provider."""
    from icoder_runtime.core import fallback_provider
    assert hasattr(fallback_provider, "make_openai_compatible_fallback")
    assert hasattr(fallback_provider, "make_azure_openai_fallback")
    assert hasattr(fallback_provider, "make_qwen_fallback")


def test_make_openai_compatible_fallback_returns_provider():
    """make_openai_compatible_fallback returns a configured BaseLLMProvider."""
    from icoder_runtime.core.fallback_provider import make_openai_compatible_fallback
    from icoder_runtime.core.llm_gateway import BaseLLMProvider
    p = make_openai_compatible_fallback(
        api_key="key", base_url="https://api.example.com/v1", model="gpt-4o-mini",
    )
    assert isinstance(p, BaseLLMProvider)
    assert p.name  # provider has a name


def test_make_azure_openai_fallback_returns_provider():
    """make_azure_openai_fallback returns a configured BaseLLMProvider."""
    from icoder_runtime.core.fallback_provider import make_azure_openai_fallback
    from icoder_runtime.core.llm_gateway import BaseLLMProvider
    p = make_azure_openai_fallback(
        api_key="key",
        endpoint="https://my-deployment.openai.azure.com",
        deployment="gpt-4o",
        api_version="2024-10-21",
    )
    assert isinstance(p, BaseLLMProvider)
    assert p.name


def test_make_qwen_fallback_returns_provider():
    """make_qwen_fallback returns a configured BaseLLMProvider."""
    from icoder_runtime.core.fallback_provider import make_qwen_fallback
    from icoder_runtime.core.llm_gateway import BaseLLMProvider
    p = make_qwen_fallback(api_key="key", model="qwen-plus")
    assert isinstance(p, BaseLLMProvider)
    assert p.name
