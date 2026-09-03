from __future__ import annotations

from app.services.model_catalog import build_model_catalog
from icoder_runtime.core.data_policy import RuntimeDataPolicy


def _policy(*, allow_external: bool = False) -> RuntimeDataPolicy:
    return RuntimeDataPolicy(
        allow_external_llm=allow_external,
        region="cn",
        egress_policy="strict",
    )


def test_selected_deepseek_reports_policy_and_credential_blockers() -> None:
    catalog = build_model_catalog(
        configured_provider="deepseek",
        configured_model="deepseek-chat",
        configured_base_url="https://api.deepseek.com/v1",
        credential_configured=False,
        data_policy=_policy(),
    )
    selected = next(item for item in catalog["models"] if item["selected"])
    assert selected["id"] == "deepseek"
    assert selected["status"] == "blocked"
    assert selected["blocking_reasons"] == [
        "credential_not_configured",
        "egress_policy_denied",
    ]
    assert catalog["live_health_verified"] is False


def test_mock_is_explicitly_development_only() -> None:
    catalog = build_model_catalog(
        configured_provider="mock",
        configured_model="ignored",
        configured_base_url="",
        credential_configured=False,
        data_policy=_policy(),
    )
    selected = next(item for item in catalog["models"] if item["selected"])
    assert selected["status"] == "development_only"
    assert selected["deployment_kind"] == "development_only"


def test_qwen_can_be_configured_for_cn_but_is_not_claimed_live() -> None:
    catalog = build_model_catalog(
        configured_provider="qwen_fallback",
        configured_model="qwen-plus",
        configured_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        credential_configured=True,
        data_policy=_policy(allow_external=True),
    )
    selected = next(item for item in catalog["models"] if item["selected"])
    assert selected["id"] == "qwen"
    assert selected["status"] == "configured_not_live_verified"
    assert selected["provider_region"] == "cn"
    assert selected["egress_decision"] == "allow"
    assert catalog["live_health_verified"] is False


def test_unknown_provider_fails_closed_in_catalog() -> None:
    catalog = build_model_catalog(
        configured_provider="mystery",
        configured_model="unknown",
        configured_base_url="https://example.com/v1",
        credential_configured=True,
        data_policy=_policy(allow_external=True),
    )
    assert catalog["models"][0]["status"] == "blocked"
    assert catalog["models"][0]["blocking_reasons"] == [
        "unsupported_provider_configuration"
    ]


def test_pinned_secondary_deployment_uses_its_own_validated_metadata() -> None:
    catalog = build_model_catalog(
        configured_provider="deepseek",
        configured_model="deepseek-chat",
        configured_base_url="https://api.deepseek.com/v1",
        credential_configured=True,
        data_policy=_policy(allow_external=True),
        tenant_selection={
            "mode": "pinned", "deployment_id": "qwen-cn-a", "version": 2,
        },
        registered_deployments=[
            {
                "id": "deepseek",
                "provider_id": "deepseek",
                "model": "deepseek-chat",
                "is_default": True,
                "tenant_selectable": True,
                "credential_configured": True,
                "endpoint_configuration_valid": True,
            },
            {
                "id": "qwen-cn-a",
                "provider_id": "qwen",
                "model": "qwen-plus",
                "is_default": False,
                "tenant_selectable": True,
                "credential_configured": True,
                "endpoint_configuration_valid": True,
            },
        ],
    )

    selected = next(item for item in catalog["models"] if item["selected"])
    assert selected["id"] == "qwen"
    assert selected["model"] == "qwen-plus"
    assert selected["status"] == "configured_not_live_verified"
    assert selected["blocking_reasons"] == []
    assert catalog["effective_deployment_id"] == "qwen-cn-a"
