"""Unit tests for DeepSeekProvider graceful degradation.

Covers Commit 3: every error path returns a degraded mock response
(degraded=True, degraded_reason, is_mock, provider="mock") instead
of raising. Real LLM success path stays unchanged.
"""
import asyncio

import httpx
import pytest

from icoder_runtime.circuit_breaker import CircuitBreaker
from icoder_runtime.core.llm_gateway import (
    DeepSeekProvider,
    _mock_fallback_response,
    gateway_circuit_breaker,
)


@pytest.fixture
def fresh_circuit(monkeypatch):
    """Replace the global gateway_circuit_breaker with a fresh one for test isolation."""
    cb = CircuitBreaker(name="test-degraded", failure_threshold=3, recovery_timeout=30.0)
    monkeypatch.setattr("icoder_runtime.core.llm_gateway.gateway_circuit_breaker", cb)
    return cb


@pytest.fixture
def no_sleep(monkeypatch):
    """Make the retry backoff a no-op so tests run instantly."""
    async def _no_sleep(*_args, **_kwargs):
        return None
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


def _success_body(content: str = "ok") -> dict:
    return {
        "id": "test-1",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "deepseek-chat",
    }


def _make_provider(transport: httpx.MockTransport | None = None) -> DeepSeekProvider:
    return DeepSeekProvider(api_key="test-key", _transport=transport)


# ── _mock_fallback_response contract ──


def test_mock_fallback_response_shape():
    """The fallback helper must always return the same shape, regardless of reason."""
    resp = _mock_fallback_response("test_reason")
    assert resp["degraded"] is True
    assert resp["degraded_reason"] == "test_reason"
    assert resp["is_mock"] is True
    assert resp["provider"] == "mock"
    assert resp["model"] == "mock/1.0"
    assert resp["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert resp["latency_ms"] == 0
    # Content must be valid JSON and include a DEGRADED_MODE issue marker
    import json
    parsed = json.loads(resp["content"])
    assert parsed["review_conclusion"] == "UNKNOWN"
    issues = parsed.get("issues_found", [])
    assert any(i.get("code") == "DEGRADED_MODE" for i in issues)


# ── Degradation: no API key ──


@pytest.mark.asyncio
async def test_no_api_key_returns_degraded_with_no_api_key_reason(monkeypatch):
    """No API key → degraded with reason='no_api_key'. No HTTP call attempted.

    Phase A A2 (2026-06-25): the dev environment persists ICODER_CREDENTIAL_LLM
    in the OS user env, so the previous ``api_key=""`` argument was being
    silently replaced by the constructor's env fallback. Explicitly clear
    the env var so this test genuinely exercises the no-key path.
    """
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be called when API key is missing")

    provider = DeepSeekProvider(api_key="", _transport=httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    assert resp["degraded"] is True
    assert resp["degraded_reason"] == "no_api_key"
    assert resp["is_mock"] is True


# ── Degradation: circuit open at entry ──


@pytest.mark.asyncio
async def test_open_circuit_short_circuits_to_degraded(monkeypatch, fresh_circuit):
    """If the global breaker is OPEN, the call short-circuits to degraded 'circuit_open'."""
    # Force the breaker open
    for _ in range(5):
        fresh_circuit.record_failure()
    assert fresh_circuit.is_open is True

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be called when circuit is open")
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    assert resp["degraded"] is True
    assert resp["degraded_reason"] == "circuit_open"
    assert resp["is_mock"] is True


# ── Degradation: 4xx (non-429/503) ──


@pytest.mark.asyncio
async def test_403_forbidden_returns_degraded(monkeypatch, fresh_circuit):
    """403 → degraded with reason 'provider_http_403', no record_failure."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    assert resp["degraded"] is True
    assert resp["degraded_reason"] == "provider_http_403"
    assert fresh_circuit.status()["failures"] == 0


# ── Degradation: network errors ──


@pytest.mark.asyncio
async def test_read_timeout_returns_degraded(monkeypatch, fresh_circuit):
    """httpx.ReadTimeout → degraded 'provider_network_error', no record_failure."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    assert resp["degraded"] is True
    assert resp["degraded_reason"] == "provider_network_error"
    assert fresh_circuit.status()["failures"] == 0


# ── Success path is unchanged ──


@pytest.mark.asyncio
async def test_success_path_does_not_tag_degraded(monkeypatch, fresh_circuit):
    """A 2xx success carries no degraded flag — callers rely on this to detect fallback."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body("real answer"))
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    assert resp["content"] == "real answer"
    assert "degraded" not in resp
    assert "is_mock" not in resp
    assert fresh_circuit.status()["state"] == "closed"


# ── Eval-loop compatibility ──


@pytest.mark.asyncio
async def test_degraded_response_never_raises_under_chaos(monkeypatch, fresh_circuit, no_sleep):
    """A burst of 429s: every call returns degraded, no raise.

    The exact reason depends on circuit state: early calls hit the
    429/503 retry path, later calls may short-circuit on
    ``circuit_open`` once the breaker trips. Either is a valid
    degraded signal — the eval loop must not crash in either case.
    """
    def chaos_handler(request: httpx.Request) -> httpx.Response:
        # Always 429 — exercises the retry path on every call until
        # the circuit opens, after which the entry check short-circuits.
        return httpx.Response(429, json={"error": "rate limited"})

    provider = _make_provider(httpx.MockTransport(chaos_handler))
    valid_reasons = {"provider_429_503", "circuit_open"}
    for i in range(5):
        resp = await provider.generate([{"role": "user", "content": f"case {i}"}])
        assert resp["degraded"] is True
        assert resp["degraded_reason"] in valid_reasons, (
            f"case {i}: unexpected reason {resp['degraded_reason']!r}"
        )
        assert resp["is_mock"] is True
    # After 5 exhausted calls, failures >= threshold, circuit is open.
    assert fresh_circuit.status()["state"] == "open"
