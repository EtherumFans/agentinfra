"""Phase A1D.4 (A1C-B-007) — LLM fallback provider factories.

Closes the A1C.9 blocker A1C-B-007: DeepSeek was the sole LLM provider.
When DeepSeek is unhealthy (circuit open, 429, network error), the
runtime returned a degraded mock response and the caller had to handle
the failure mode. Charter §4 PDF asks for ≥1 fallback provider so the
runtime keeps serving.

This module exposes factory helpers that return ``BaseLLMProvider``
subclasses configured for common fallback scenarios. The factories
build on the existing ``OpenAICompatibleProvider`` — any OpenAI-
compatible endpoint works.

Real API keys are deferred to Pilot env (per Charter §五 environmental
hard blockers). Local / dev / CI uses the factories with placeholder
keys; the resulting provider's health_check reports "missing" but the
type-system contract is satisfied.

Factory list:
  - ``make_openai_compatible_fallback(api_key, base_url, model, ...)``
    Generic factory — any OpenAI-compatible endpoint.
  - ``make_azure_openai_fallback(api_key, endpoint, deployment, api_version)``
    Azure OpenAI Service (Chat OpenAI compatible with deployment path).
  - ``make_qwen_fallback(api_key, model, ...)``
    Alibaba Qwen (DashScope OpenAI-compatible endpoint).
  - ``make_moonshot_fallback(api_key, model, ...)``
    Moonshot AI Kimi (OpenAI-compatible).
"""
from __future__ import annotations

from typing import Any

from icoder_runtime.core.llm_gateway import OpenAICompatibleProvider


def make_openai_compatible_fallback(
    *,
    api_key: str = "",
    base_url: str,
    model: str,
    name: str = "openai_compat_fallback",
    max_tokens: int = 4096,
    temperature: float = 0.1,
    timeout: int = 120,
    **kwargs: Any,
) -> OpenAICompatibleProvider:
    """Construct a generic OpenAI-compatible fallback provider.

    Suitable for: Azure OpenAI (when given the deployment-scoped endpoint),
    Qwen DashScope, Moonshot Kimi, self-hosted vLLM, Together AI, etc.

    Required params:
      - ``base_url`` — fully-qualified URL ending at ``/v1`` or equivalent
        OpenAI-compatible root.
      - ``model`` — the model identifier the endpoint expects in
        ``payload["model"]``.

    Optional params mirror ``DeepSeekProvider`` so the failover target
    has the same call shape as the primary.
    """
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        _name_override=name,
        **kwargs,
    )


def make_azure_openai_fallback(
    *,
    api_key: str = "",
    endpoint: str,
    deployment: str,
    api_version: str = "2024-10-21",
    name: str = "azure_openai_fallback",
    max_tokens: int = 4096,
    temperature: float = 0.1,
    timeout: int = 120,
) -> OpenAICompatibleProvider:
    """Construct an Azure OpenAI fallback provider.

    Azure uses deployment-scoped URLs of the form::

        https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions?api-version={api_version}

    The factory expands the template; the resulting provider uses
    ``api-key`` header (not ``Authorization: Bearer``) for auth — set
    via the ``auth_header`` kwarg on ``OpenAICompatibleProvider``.
    """
    base_url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        f"/chat/completions?api-version={api_version}"
    )
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=deployment,  # Azure uses deployment name as "model" in payload
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        _name_override=name,
        auth_header="api-key",
    )


def make_qwen_fallback(
    *,
    api_key: str = "",
    model: str = "qwen-plus",
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    name: str = "qwen_fallback",
    max_tokens: int = 4096,
    temperature: float = 0.1,
    timeout: int = 120,
) -> OpenAICompatibleProvider:
    """Construct an Alibaba Qwen (DashScope) fallback provider.

    DashScope's OpenAI-compatible mode is documented at:
    https://help.aliyun.com/zh/dashscope/developer-reference/compatibility-of-openai-with-dashscope
    """
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        _name_override=name,
    )


def make_moonshot_fallback(
    *,
    api_key: str = "",
    model: str = "moonshot-v1-32k",
    base_url: str = "https://api.moonshot.cn/v1",
    name: str = "moonshot_fallback",
    max_tokens: int = 4096,
    temperature: float = 0.1,
    timeout: int = 120,
) -> OpenAICompatibleProvider:
    """Construct a Moonshot AI (Kimi) fallback provider.

    Moonshot's OpenAI-compatible endpoint is documented at:
    https://platform.moonshot.cn/docs
    """
    return OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        _name_override=name,
    )


__all__ = [
    "make_openai_compatible_fallback",
    "make_azure_openai_fallback",
    "make_qwen_fallback",
    "make_moonshot_fallback",
]
