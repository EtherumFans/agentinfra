"""Phase 4-G #1 — Live cost computation tests.

Verifies the `_compute_cost_usd` helper in `icoder_runtime.core.llm_gateway`
correctly converts `usage.input_tokens` + `usage.output_tokens` to a USD cost,
and that DeepSeekProvider/OpenAICompatibleProvider populate `cost_usd` in
their `generate()` result dict so the cost flows through to `AgentRunResponse.cost`.

Covers:
  - helper returns 0.0 for empty/None/zero usage
  - helper computes per-1M-token pricing from settings (defaults: 0.14/0.28)
  - DeepSeekProvider result dict contains `cost_usd` (mocked HTTP)
  - OpenAICompatibleProvider result dict contains `cost_usd` (mocked HTTP)
"""
from __future__ import annotations

from icoder_runtime.core.llm_gateway import (
    _compute_cost_usd,
    DeepSeekProvider,
    OpenAICompatibleProvider,
)


# ── Helper: pure-function cases ────────────────────────────────────────


def test_compute_cost_usd_zero_for_empty_usage():
    assert _compute_cost_usd({}) == 0.0
    assert _compute_cost_usd(None) == 0.0  # type: ignore[arg-type]
    assert _compute_cost_usd({"input_tokens": 0, "output_tokens": 0}) == 0.0


def test_compute_cost_usd_matches_default_pricing():
    # Defaults: $0.14 / 1M input + $0.28 / 1M output
    cost = _compute_cost_usd({"input_tokens": 1_500, "output_tokens": 300})
    expected = (1_500 / 1_000_000) * 0.14 + (300 / 1_000_000) * 0.28
    assert abs(cost - expected) < 1e-9
    assert cost == 0.000294


def test_compute_cost_usd_handles_string_tokens():
    # Some providers return string-typed token counts; coerce defensively.
    cost = _compute_cost_usd({"input_tokens": "1000", "output_tokens": "200"})
    assert cost > 0
    expected = (1000 / 1_000_000) * 0.14 + (200 / 1_000_000) * 0.28
    assert abs(cost - expected) < 1e-9


# ── DeepSeekProvider.generate() result dict ──────────────────────────


class _FakeResponse:
    """Minimal stand-in for httpx.Response for DeepSeek JSON parsing."""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient."""

    def __init__(self, payload: dict):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None, **kwargs):
        return _FakeResponse(self._payload)


def _patch_httpx(monkeypatch, payload):
    """Replace httpx.AsyncClient with our fake so DeepSeekProvider.generate works."""
    import httpx

    def fake_client(timeout=None):
        return _FakeAsyncClient(payload)
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


def test_deepseek_provider_result_includes_cost_usd(monkeypatch):
    payload = {
        "model": "deepseek-chat",
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 2000, "completion_tokens": 500},
    }
    _patch_httpx(monkeypatch, payload)

    provider = DeepSeekProvider(api_key="sk-test", model="deepseek-chat")
    import asyncio
    result = asyncio.run(provider.generate(messages=[{"role": "user", "content": "hi"}]))

    assert "cost_usd" in result
    assert result["cost_usd"] > 0
    expected = (2000 / 1_000_000) * 0.14 + (500 / 1_000_000) * 0.28
    assert abs(result["cost_usd"] - expected) < 1e-9
    # usage still surfaces for callers that want raw token counts
    assert result["usage"]["input_tokens"] == 2000
    assert result["usage"]["output_tokens"] == 500


def test_openai_compat_provider_result_includes_cost_usd(monkeypatch):
    payload = {
        "model": "llama3",
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    _patch_httpx(monkeypatch, payload)

    provider = OpenAICompatibleProvider(api_key="not-needed", model="llama3")
    import asyncio
    result = asyncio.run(provider.generate(messages=[{"role": "user", "content": "hi"}]))

    assert "cost_usd" in result
    assert result["cost_usd"] > 0
    expected = (100 / 1_000_000) * 0.14 + (50 / 1_000_000) * 0.28
    assert abs(result["cost_usd"] - expected) < 1e-9
