from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from icoder_runtime.core.data_policy import RuntimeDataPolicy
from icoder_runtime.core.llm_gateway import BaseLLMProvider, LLMGateway
from icoder_runtime.core.errors import LLMProviderNotConfigured
from icoder_runtime.core.registry import RuntimeAgentRegistry
from icoder_runtime.embedded.platform_runtime import PlatformRuntime


class RecordingProvider(BaseLLMProvider):
    def __init__(self, name: str) -> None:
        self.name = name
        self.generate_calls = 0
        self.stream_calls = 0

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.generate_calls += 1
        return {
            "content": "ok",
            "model": "test",
            "provider": self.name,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self.stream_calls += 1
        yield {"type": "delta", "text": "ok"}
        yield {"type": "completed", "result": await self.generate(messages)}


class DegradedRecordingProvider(RecordingProvider):
    async def generate(self, *args, **kwargs) -> dict[str, Any]:
        self.generate_calls += 1
        return {"degraded": True, "degraded_reason": "test_degraded"}


def _cn_policy(*, allow_external: bool = False) -> RuntimeDataPolicy:
    return RuntimeDataPolicy(
        allow_external_llm=allow_external,
        region="cn",
        egress_policy="strict",
    )


@pytest.mark.asyncio
async def test_generate_denies_external_provider_before_invocation() -> None:
    provider = RecordingProvider("deepseek")
    gateway = LLMGateway(data_policy=_cn_policy()).register(provider, default=True)

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert provider.generate_calls == 0
    assert result["degraded"] is True
    assert result["degraded_reason"] == "provider_egress_denied"
    assert result["blocked_provider"] == "deepseek"
    assert result["egress_decision"]["decision"] == "deny"
    assert "api_key" not in str(result).lower()


@pytest.mark.asyncio
async def test_generate_can_fail_over_from_blocked_external_to_local() -> None:
    primary = RecordingProvider("deepseek")
    local = RecordingProvider("local")
    gateway = LLMGateway(data_policy=_cn_policy()).register(primary, default=True)
    gateway.register_fallback(local)

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert primary.generate_calls == 0
    assert local.generate_calls == 1
    assert result["provider"] == "local"
    assert result["fallback_from"] == "deepseek"
    assert result["fallback_reason"] == "provider_egress_denied"


@pytest.mark.asyncio
async def test_stream_denies_provider_without_emitting_native_delta() -> None:
    provider = RecordingProvider("qwen_fallback")
    gateway = LLMGateway(data_policy=_cn_policy()).register(provider, default=True)

    events = [
        event
        async for event in gateway.generate_stream(
            [{"role": "user", "content": "hello"}]
        )
    ]

    assert provider.stream_calls == 0
    assert [event["type"] for event in events] == ["completed"]
    assert events[0]["result"]["degraded_reason"] == "provider_egress_denied"
    assert events[0]["result"]["egress_decision"]["provider_name"] == "qwen"


@pytest.mark.asyncio
async def test_qwen_alias_is_allowed_only_when_external_llm_is_enabled() -> None:
    provider = RecordingProvider("qwen_fallback")
    gateway = LLMGateway(data_policy=_cn_policy(allow_external=True)).register(
        provider,
        default=True,
    )

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert provider.generate_calls == 1
    assert result["provider"] == "qwen_fallback"


@pytest.mark.asyncio
async def test_embedded_runtime_default_gateway_enforces_env_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "false")
    monkeypatch.setenv("ICODER_REGION", "cn")
    monkeypatch.setenv("ICODER_EGRESS_POLICY", "strict")
    provider = RecordingProvider("deepseek")
    runtime = PlatformRuntime(
        registry=RuntimeAgentRegistry(storage_dir=tmp_path),
    )
    runtime._gateway.register(provider, default=True)

    result = await runtime._gateway.generate(
        [{"role": "user", "content": "hello"}],
    )

    assert provider.generate_calls == 0
    assert result["degraded_reason"] == "provider_egress_denied"


@pytest.mark.asyncio
async def test_tenant_pinned_deployment_routes_exactly() -> None:
    async def resolver(_context):
        return {"mode": "pinned", "deployment_id": "qwen", "version": 3}

    deepseek = RecordingProvider("deepseek")
    qwen = RecordingProvider("qwen")
    gateway = LLMGateway(
        data_policy=_cn_policy(allow_external=True),
        tenant_provider_resolver=resolver,
    ).register(deepseek, default=True)
    gateway.register(qwen)

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert deepseek.generate_calls == 0
    assert qwen.generate_calls == 1
    assert result["provider"] == "qwen"
    assert result["model_routing"] == {
        "mode": "pinned",
        "deployment_id": "qwen",
        "selection_version": 3,
        "decision": "allow",
    }


@pytest.mark.asyncio
async def test_unknown_tenant_deployment_fails_closed_without_default() -> None:
    async def resolver(_context):
        return {"mode": "pinned", "deployment_id": "retired", "version": 4}

    default = RecordingProvider("deepseek")
    fallback = RecordingProvider("local")
    gateway = LLMGateway(
        data_policy=_cn_policy(allow_external=True),
        tenant_provider_resolver=resolver,
    ).register(default, default=True)
    gateway.register_fallback(fallback)

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert default.generate_calls == 0
    assert fallback.generate_calls == 0
    assert result["degraded_reason"] == "tenant_model_deployment_unavailable"
    assert result["model_routing"]["decision"] == "deny"


@pytest.mark.asyncio
async def test_pinned_deployment_never_uses_global_fallback() -> None:
    async def resolver(_context):
        return {"mode": "pinned", "deployment_id": "qwen", "version": 5}

    pinned = DegradedRecordingProvider("qwen")
    fallback = RecordingProvider("local")
    gateway = LLMGateway(
        data_policy=_cn_policy(allow_external=True),
        tenant_provider_resolver=resolver,
    ).register(pinned, default=True)
    gateway.register_fallback(fallback)

    result = await gateway.generate([{"role": "user", "content": "hello"}])

    assert pinned.generate_calls == 1
    assert fallback.generate_calls == 0
    assert result["degraded_reason"] == "test_degraded"
    assert result["model_routing"]["deployment_id"] == "qwen"


def test_unknown_explicit_provider_does_not_fall_back_to_default() -> None:
    gateway = LLMGateway().register(RecordingProvider("local"), default=True)

    with pytest.raises(LLMProviderNotConfigured, match="not registered"):
        gateway.get("retired-deployment")


@pytest.mark.asyncio
async def test_explicit_provider_cannot_bypass_pinned_tenant_deployment() -> None:
    async def resolver(_context):
        return {"mode": "pinned", "deployment_id": "local", "version": 6}

    deepseek = RecordingProvider("deepseek")
    local = RecordingProvider("local")
    gateway = LLMGateway(
        tenant_provider_resolver=resolver,
    ).register(deepseek, default=True)
    gateway.register(local)

    result = await gateway.generate(
        [{"role": "user", "content": "hello"}],
        provider="deepseek",
    )

    assert deepseek.generate_calls == 0
    assert local.generate_calls == 0
    assert result["degraded_reason"] == "tenant_model_deployment_conflict"
    assert result["model_routing"]["decision"] == "deny"
