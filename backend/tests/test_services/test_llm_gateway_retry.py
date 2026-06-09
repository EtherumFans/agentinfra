"""Unit tests for DeepSeekProvider retry logic with exponential backoff.

Covers Commit 2: 429/503 retry, 401/400 no-retry, circuit breaker integration.
Commit 3: error paths return a degraded mock response (never raise).
"""
import asyncio

import httpx
import pytest

from icoder_runtime.circuit_breaker import CircuitBreaker
from icoder_runtime.core.errors import ProviderError
from icoder_runtime.core.llm_gateway import DeepSeekProvider


@pytest.fixture
def fresh_circuit(monkeypatch):
    """Replace the global gateway_circuit_breaker with a fresh one for test isolation."""
    cb = CircuitBreaker(name="test-deepseek", failure_threshold=3, recovery_timeout=30.0)
    monkeypatch.setattr("icoder_runtime.core.llm_gateway.gateway_circuit_breaker", cb)
    return cb


@pytest.fixture
def no_sleep(monkeypatch):
    """Make the retry backoff a no-op so tests run instantly."""
    async def _no_sleep(*_args, **_kwargs):
        return None
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)


def _mock_transport(responses: list[tuple[int, dict]]):
    """Build a handler that returns responses in order and records every call."""
    calls: list[httpx.Request] = []
    iter_resp = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        status, body = next(iter_resp)
        return httpx.Response(status, json=body)

    return handler, calls


def _success_body(content: str = "ok") -> dict:
    return {
        "id": "test-1",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "deepseek-chat",
    }


def _make_provider(transport: httpx.MockTransport) -> DeepSeekProvider:
    return DeepSeekProvider(api_key="test-key", _transport=transport)


def _assert_degraded(resp: dict, expected_reason: str) -> None:
    """Assert the response carries the degraded contract fields."""
    assert resp.get("degraded") is True, f"expected degraded=True, got {resp}"
    assert resp.get("degraded_reason") == expected_reason, (
        f"expected degraded_reason={expected_reason!r}, got {resp.get('degraded_reason')!r}"
    )
    assert resp.get("is_mock") is True
    assert resp.get("provider") == "mock"


@pytest.mark.asyncio
async def test_retry_429_twice_then_200(monkeypatch, fresh_circuit, no_sleep):
    """429 twice then 200 → 3 calls, final OK, circuit remains closed (success recorded)."""
    handler, calls = _mock_transport([
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
        (200, _success_body("recovered")),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    result = await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 3
    assert result["content"] == "recovered"
    assert "degraded" not in result  # success path does not tag degraded
    status = fresh_circuit.status()
    assert status["state"] == "closed"
    assert status["failures"] == 0


@pytest.mark.asyncio
async def test_401_no_retry_returns_degraded(fresh_circuit):
    """401 returns degraded on first call, no retry, no record_failure."""
    handler, calls = _mock_transport([
        (401, {"error": "unauthorized"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    _assert_degraded(resp, "provider_http_401")
    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_400_no_retry_returns_degraded(fresh_circuit):
    """400 (bad request) is non-retryable; returns degraded without touching the circuit."""
    handler, calls = _mock_transport([
        (400, {"error": "bad request"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    _assert_degraded(resp, "provider_http_400")
    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_429_exhausted_records_one_failure_returns_degraded(
    monkeypatch, fresh_circuit, no_sleep
):
    """Exhausted 429: 3 attempts, 1 circuit failure, returns degraded (does not raise)."""
    handler, calls = _mock_transport([
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 3
    _assert_degraded(resp, "provider_429_503")
    assert fresh_circuit.status()["failures"] == 1
    assert fresh_circuit.status()["state"] == "closed"


@pytest.mark.asyncio
async def test_three_exhausted_calls_open_circuit(monkeypatch, fresh_circuit, no_sleep):
    """Three consecutive exhausted calls trip the breaker to OPEN."""
    handler, calls = _mock_transport([
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
    ] * 3)
    provider = _make_provider(httpx.MockTransport(handler))

    for _ in range(3):
        resp = await provider.generate([{"role": "user", "content": "hi"}])
        _assert_degraded(resp, "provider_429_503")

    assert len(calls) == 9
    assert fresh_circuit.status()["state"] == "open"


@pytest.mark.asyncio
async def test_503_once_then_200(monkeypatch, fresh_circuit, no_sleep):
    """503 once then 200 → 2 calls, success, circuit stays clean."""
    handler, calls = _mock_transport([
        (503, {"error": "service unavailable"}),
        (200, _success_body("two calls only")),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    result = await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 2
    assert result["content"] == "two calls only"
    assert "degraded" not in result
    assert fresh_circuit.status()["state"] == "closed"


@pytest.mark.asyncio
async def test_network_timeout_returns_degraded_no_circuit_failure(fresh_circuit):
    """httpx.ConnectError → degraded mock, no record_failure, no raise."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _make_provider(httpx.MockTransport(handler))

    resp = await provider.generate([{"role": "user", "content": "hi"}])

    _assert_degraded(resp, "provider_network_error")
    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_missing_api_key_returns_degraded_without_http():
    """No api_key → degraded mock before any HTTP call. No record_failure."""
    provider = DeepSeekProvider(api_key="")

    resp = await provider.generate([{"role": "user", "content": "hi"}])
    _assert_degraded(resp, "no_api_key")
