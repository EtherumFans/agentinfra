"""Create the operator-selected primary LLM adapter without network access."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from icoder_runtime.core.data_policy import normalize_provider_name
from icoder_runtime.core.llm_gateway import (
    BaseLLMProvider,
    DeepSeekProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
)


SUPPORTED_PRIMARY_PROVIDERS = frozenset({
    "deepseek",
    "qwen",
    "openai_compat",
    "local",
    "mock",
})

_DEPLOYMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_CREDENTIAL_ENV_RE = re.compile(r"^ICODER_CREDENTIAL_LLM_[A-Z0-9_]+$")
_DEPLOYMENT_ALLOWED_KEYS = frozenset({
    "id",
    "provider",
    "model",
    "base_url",
    "credential_env",
    "tenant_selectable",
})
_SECRET_KEYS = frozenset({"api_key", "key", "secret", "credential"})


class NamedProviderDeployment(BaseLLMProvider):
    """Give one configured provider/model pair a stable routing identifier."""

    def __init__(
        self,
        *,
        deployment_id: str,
        provider_id: str,
        inner: BaseLLMProvider,
    ) -> None:
        self.name = deployment_id
        self.policy_provider_name = provider_id
        self._inner = inner

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = await self._inner.generate(
            messages=messages,
            tools=tools,
            response_schema=response_schema,
            context=context,
        )
        if isinstance(result, dict):
            result.setdefault("deployment_id", self.name)
            result.setdefault("provider_family", self.policy_provider_name)
        return result

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for event in self._inner.generate_stream(
            messages=messages,
            tools=tools,
            response_schema=response_schema,
            context=context,
        ):
            if isinstance(event, dict):
                yield {
                    **event,
                    "deployment_id": self.name,
                    "provider_family": self.policy_provider_name,
                }

    def health_check(self) -> dict[str, Any]:
        inner = self._inner.health_check()
        return {
            "deployment_id": self.name,
            "provider": self.policy_provider_name,
            "status": inner.get("status", "unknown"),
            "mode": inner.get("mode", "configured"),
        }


def create_configured_llm_deployments(
    raw_json: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> list[tuple[BaseLLMProvider, dict[str, Any]]]:
    """Build extra operator deployments without accepting inline secrets.

    ``ICODER_LLM_DEPLOYMENTS_JSON`` contains only deployment metadata and a
    *name* of a credential environment variable. The credential value is
    resolved separately and never copied into the returned public metadata.
    """

    env = os.environ if environ is None else environ
    raw = raw_json if raw_json is not None else env.get(
        "ICODER_LLM_DEPLOYMENTS_JSON", ""
    )
    if not str(raw or "").strip():
        return []
    try:
        payload = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("ICODER_LLM_DEPLOYMENTS_JSON must be valid JSON") from exc
    if not isinstance(payload, list) or len(payload) > 16:
        raise ValueError("LLM deployments must be a JSON array with at most 16 items")

    deployments: list[tuple[BaseLLMProvider, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"LLM deployment at index {index} must be an object")
        lowered_keys = {str(key).lower() for key in item}
        if lowered_keys.intersection(_SECRET_KEYS):
            raise ValueError("Inline LLM credentials are forbidden")
        unknown = sorted(set(item).difference(_DEPLOYMENT_ALLOWED_KEYS))
        if unknown:
            raise ValueError(f"Unsupported LLM deployment fields: {unknown}")

        deployment_id = str(item.get("id") or "").strip().lower()
        provider_id = normalize_provider_name(str(item.get("provider") or ""))
        model = str(item.get("model") or "").strip()
        base_url = str(item.get("base_url") or "").strip()
        credential_env = str(item.get("credential_env") or "").strip()
        if not _DEPLOYMENT_ID_RE.fullmatch(deployment_id):
            raise ValueError(f"Invalid LLM deployment id at index {index}")
        if deployment_id in seen or deployment_id in {"mock", "medical_coding"}:
            raise ValueError(f"Duplicate or reserved LLM deployment id: {deployment_id}")
        if provider_id not in SUPPORTED_PRIMARY_PROVIDERS - {"mock"}:
            raise ValueError(f"Unsupported deployment provider: {provider_id}")
        if not model or not base_url:
            raise ValueError(f"Deployment {deployment_id} requires model and base_url")
        parsed_url = urlparse(base_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError(f"Deployment {deployment_id} has an invalid base_url")
        if provider_id != "local" and parsed_url.scheme != "https":
            raise ValueError(f"Deployment {deployment_id} external base_url must use HTTPS")
        if credential_env and not _CREDENTIAL_ENV_RE.fullmatch(credential_env):
            raise ValueError(f"Deployment {deployment_id} has an invalid credential_env")
        if provider_id != "local" and not credential_env:
            raise ValueError(f"Deployment {deployment_id} requires credential_env")
        api_key = str(env.get(credential_env, "")) if credential_env else ""
        if provider_id != "local" and not api_key.strip():
            raise ValueError(f"Deployment {deployment_id} credential is not configured")

        inner = create_primary_llm_provider(
            provider_name=provider_id,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        deployment = NamedProviderDeployment(
            deployment_id=deployment_id,
            provider_id=provider_id,
            inner=inner,
        )
        metadata = {
            "id": deployment_id,
            "provider_id": provider_id,
            "model": model,
            "is_default": False,
            "tenant_selectable": bool(item.get("tenant_selectable", True)),
            "credential_configured": bool(api_key.strip()),
            "endpoint_configuration_valid": True,
        }
        deployments.append((deployment, metadata))
        seen.add(deployment_id)
    return deployments


def create_primary_llm_provider(
    *,
    provider_name: str,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int = 4096,
    temperature: float = 0.1,
    timeout: int = 120,
) -> BaseLLMProvider:
    provider_id = normalize_provider_name(provider_name or "mock")
    if provider_id not in SUPPORTED_PRIMARY_PROVIDERS:
        raise ValueError(f"unsupported LLM_PROVIDER: {provider_id}")
    if provider_id == "mock":
        return MockLLMProvider()
    if not base_url.strip():
        raise ValueError(f"LLM_BASE_URL is required for provider {provider_id}")

    common = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "timeout": timeout,
    }
    if provider_id == "deepseek":
        if "dashscope.aliyuncs.com" in base_url.lower():
            raise ValueError("DeepSeek provider cannot use the Qwen DashScope endpoint")
        return DeepSeekProvider(**common)
    if provider_id == "qwen" and "deepseek.com" in base_url.lower():
        raise ValueError("Qwen provider cannot use the DeepSeek endpoint")
    if provider_id == "local" and (
        "deepseek.com" in base_url.lower()
        or "dashscope.aliyuncs.com" in base_url.lower()
    ):
        raise ValueError("Local provider requires a hospital/self-hosted endpoint")

    return OpenAICompatibleProvider(
        **{
            **common,
            "api_key": api_key or ("not-needed" if provider_id == "local" else ""),
        },
        _name_override=provider_id,
    )
