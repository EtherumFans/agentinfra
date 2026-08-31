from __future__ import annotations

import pytest

from icoder_runtime.core.llm_gateway import (
    DeepSeekProvider,
    MockLLMProvider,
    OpenAICompatibleProvider,
)
from icoder_runtime.core.llm_provider_factory import (
    NamedProviderDeployment,
    create_configured_llm_deployments,
    create_primary_llm_provider,
)


def _build(provider: str, base_url: str, api_key: str = "test-only"):
    return create_primary_llm_provider(
        provider_name=provider,
        api_key=api_key,
        base_url=base_url,
        model="test-model",
    )


def test_builds_deepseek_without_network_access() -> None:
    provider = _build("deepseek", "https://api.deepseek.com/v1")
    assert isinstance(provider, DeepSeekProvider)
    assert provider.name == "deepseek"


def test_builds_qwen_as_named_openai_compatible_provider() -> None:
    provider = _build(
        "qwen",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "qwen"


def test_builds_no_key_local_provider_for_hospital_endpoint() -> None:
    provider = _build("local", "http://model-gateway.hospital.local/v1", api_key="")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "local"
    assert provider.api_key == "not-needed"


def test_mock_mode_never_constructs_external_provider() -> None:
    provider = _build("mock", "", api_key="should-not-be-used")
    assert isinstance(provider, MockLLMProvider)


@pytest.mark.parametrize(
    ("provider", "endpoint"),
    [
        ("qwen", "https://api.deepseek.com/v1"),
        ("deepseek", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("local", "https://api.deepseek.com/v1"),
    ],
)
def test_rejects_obvious_provider_endpoint_mismatch(provider: str, endpoint: str) -> None:
    with pytest.raises(ValueError):
        _build(provider, endpoint)


def test_rejects_unsupported_provider_instead_of_silently_using_deepseek() -> None:
    with pytest.raises(ValueError, match="unsupported LLM_PROVIDER"):
        _build("unreviewed-provider", "https://example.com/v1")


def test_builds_named_multi_deployment_without_exposing_credential() -> None:
    deployments = create_configured_llm_deployments(
        """[{
          "id": "qwen-cn-a",
          "provider": "qwen",
          "model": "qwen-plus",
          "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
          "credential_env": "ICODER_CREDENTIAL_LLM_QWEN_A"
        }]""",
        environ={"ICODER_CREDENTIAL_LLM_QWEN_A": "test-only-secret"},
    )

    provider, public = deployments[0]
    assert isinstance(provider, NamedProviderDeployment)
    assert provider.name == "qwen-cn-a"
    assert provider.policy_provider_name == "qwen"
    assert public == {
        "id": "qwen-cn-a",
        "provider_id": "qwen",
        "model": "qwen-plus",
        "is_default": False,
        "tenant_selectable": True,
        "credential_configured": True,
        "endpoint_configuration_valid": True,
    }
    assert "secret" not in str(public).lower()
    assert "base_url" not in public


@pytest.mark.parametrize(
    "raw,environ,match",
    [
        (
            '[{"id":"qwen","provider":"qwen","model":"qwen-plus",'
            '"base_url":"https://example.com/v1","api_key":"inline"}]',
            {},
            "Inline LLM credentials",
        ),
        (
            '[{"id":"qwen","provider":"qwen","model":"qwen-plus",'
            '"base_url":"http://example.com/v1",'
            '"credential_env":"ICODER_CREDENTIAL_LLM_QWEN"}]',
            {"ICODER_CREDENTIAL_LLM_QWEN": "test"},
            "must use HTTPS",
        ),
        (
            '[{"id":"qwen","provider":"qwen","model":"qwen-plus",'
            '"base_url":"https://example.com/v1",'
            '"credential_env":"DEEPSEEK_API_KEY"}]',
            {"DEEPSEEK_API_KEY": "test"},
            "invalid credential_env",
        ),
        (
            '[{"id":"qwen","provider":"qwen","model":"qwen-plus",'
            '"base_url":"https://example.com/v1",'
            '"credential_env":"ICODER_CREDENTIAL_LLM_QWEN"}]',
            {},
            "credential is not configured",
        ),
    ],
)
def test_rejects_unsafe_multi_deployment_configuration(
    raw: str,
    environ: dict[str, str],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        create_configured_llm_deployments(raw, environ=environ)
