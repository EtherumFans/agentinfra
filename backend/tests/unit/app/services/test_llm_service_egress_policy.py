from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.llm_service import (
    LLMProviderCallError,
    LLMService,
    _classify_provider_error,
    _ensure_llm_call_allowed,
)


def test_legacy_llm_service_blocks_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "true")
    with pytest.raises(RuntimeError, match="development-only"):
        _ensure_llm_call_allowed()


def test_legacy_llm_service_blocks_external_provider_when_egress_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "false")
    with pytest.raises(RuntimeError, match="egress denied"):
        _ensure_llm_call_allowed()


def test_legacy_llm_service_allows_cn_qwen_when_operator_enables_egress(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.setenv("ICODER_REGION", "cn")
    monkeypatch.setenv("ICODER_EGRESS_POLICY", "strict")
    _ensure_llm_call_allowed()


def test_legacy_llm_service_blocks_cross_region_openai_compatible_endpoint(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.setenv("ICODER_REGION", "cn")
    monkeypatch.setenv("ICODER_EGRESS_POLICY", "strict")
    monkeypatch.delenv("ICODER_PROVIDER_REGION_OPENAI_COMPAT", raising=False)
    with pytest.raises(RuntimeError, match="does not match tenant region"):
        _ensure_llm_call_allowed()


@pytest.mark.asyncio
async def test_llm_service_exposes_only_bounded_retry_diagnostics(monkeypatch) -> None:
    class ProviderError(Exception):
        status_code = 429

    async def create(**_kwargs):
        raise ProviderError("sensitive provider payload must not escape")

    breaker = SimpleNamespace(
        is_open=False,
        record_failure=lambda: None,
        record_success=lambda: None,
    )
    monkeypatch.setattr("app.services.llm_service._ensure_llm_call_allowed", lambda: None)
    monkeypatch.setattr("app.services.llm_service.llm_circuit_breaker", breaker)
    monkeypatch.setattr("app.services.llm_service.asyncio.sleep", _no_sleep)
    service = LLMService.__new__(LLMService)
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    service.model = "deepseek-chat"
    service.max_tokens = 64
    service.temperature = 0.1
    service.max_retries = 1

    with pytest.raises(LLMProviderCallError) as captured:
        await service.chat(messages=[{"role": "user", "content": "bounded test"}])

    error = captured.value
    assert error.category == "rate_limit"
    assert error.status_code == 429
    assert error.attempts == 2
    assert error.retryable is True
    assert "sensitive provider payload" not in str(error)


def test_provider_error_classifier_does_not_return_provider_content() -> None:
    error = ConnectionError("patient text and credential-shaped content")

    assert _classify_provider_error(error) == ("connection", None)


async def _no_sleep(_seconds: float) -> None:
    return None
