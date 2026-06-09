"""Unit tests for DeepSeekProvider retry logic with exponential backoff.

Covers Commit 2: 429/503 retry, 401/400 no-retry, circuit breaker integration.
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
    """Build a handler that returns responses in order and records every call.

    Returns (handler, calls_list).
    """
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
    status = fresh_circuit.status()
    assert status["state"] == "closed"
    assert status["failures"] == 0


@pytest.mark.asyncio
async def test_401_no_retry_no_circuit_failure(fresh_circuit):
    """401 raises immediately on first call, no retry, no record_failure."""
    handler, calls = _mock_transport([
        (401, {"error": "unauthorized"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderError, match="401"):
        await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_400_no_retry_no_circuit_failure(fresh_circuit):
    """400 (bad request) is non-retryable; raises without touching the circuit."""
    handler, calls = _mock_transport([
        (400, {"error": "bad request"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderError, match="400"):
        await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 1
    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_429_exhausted_records_one_failure_per_call(monkeypatch, fresh_circuit, no_sleep):
    """Each exhausted generate() call records exactly one circuit failure.

    The contract is per-call, not per-attempt: 3 retries inside one call
    count as a single failure signal, since the failure pattern is
    "provider is unhealthy" rather than "three distinct failures."
    """
    handler, calls = _mock_transport([
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
    ])
    provider = _make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderError, match="429"):
        await provider.generate([{"role": "user", "content": "hi"}])

    assert len(calls) == 3
    # Single exhausted call → exactly 1 failure recorded; state still CLOSED
    # because threshold is 3.
    assert fresh_circuit.status()["failures"] == 1
    assert fresh_circuit.status()["state"] == "closed"


@pytest.mark.asyncio
async def test_three_exhausted_calls_open_circuit(monkeypatch, fresh_circuit, no_sleep):
    """Three consecutive exhausted generate() calls trip the breaker to OPEN."""
    handler, calls = _mock_transport([
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
        (429, {"error": "rate limited"}),
    ] * 3)
    provider = _make_provider(httpx.MockTransport(handler))

    for _ in range(3):
        with pytest.raises(ProviderError, match="429"):
            await provider.generate([{"role": "user", "content": "hi"}])

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
    assert fresh_circuit.status()["state"] == "closed"


@pytest.mark.asyncio
async def test_network_timeout_no_retry_raises(monkeypatch, fresh_circuit):
    """httpx.ConnectError (network failure) re-raises as ProviderError without retry.

    Connection-level errors follow the previous single-attempt behavior; the
    higher-level retry / fallback is wired in Commit 3.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderError, match="[Cc]onnect.*refused|API error"):
        await provider.generate([{"role": "user", "content": "hi"}])

    assert fresh_circuit.status()["failures"] == 0


@pytest.mark.asyncio
async def test_missing_api_key_raises_before_http():
    """No api_key → ProviderError before any HTTP call. No record_failure."""
    provider = DeepSeekProvider(api_key="")  # no env, no arg

    with pytest.raises(ProviderError, match="API key not configured"):
        await provider.generate([{"role": "user", "content": "hi"}])
