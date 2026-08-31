"""Truthful LLM provider catalog for the Console and deployment audits.

The catalog reports operator configuration and policy readiness only.  It does
not perform network probes and therefore never labels an external model as
healthy or production-ready merely because a credential exists.
"""

from __future__ import annotations

from typing import Any

from icoder_runtime.core.data_policy import RuntimeDataPolicy, normalize_provider_name


_COMMON_CAPABILITIES = ["chat", "streaming", "tool_calling", "structured_output"]

MODEL_PROVIDER_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "deepseek",
        "display_name": "DeepSeek",
        "default_model": "deepseek-chat",
        "deployment_kind": "external_api",
        "credential_required": True,
        "adapter_capabilities": _COMMON_CAPABILITIES,
        "china_scenario": "Mainland China provider option; hospital approval remains required.",
    },
    {
        "id": "qwen",
        "display_name": "Qwen / 通义千问",
        "default_model": "qwen-plus",
        "deployment_kind": "external_api",
        "credential_required": True,
        "adapter_capabilities": _COMMON_CAPABILITIES,
        "china_scenario": "OpenAI-compatible mainland China fallback option.",
    },
    {
        "id": "openai_compat",
        "display_name": "OpenAI-compatible Endpoint",
        "default_model": "operator-defined",
        "deployment_kind": "external_or_private_api",
        "credential_required": True,
        "adapter_capabilities": _COMMON_CAPABILITIES,
        "china_scenario": "Region must be explicitly declared for the concrete endpoint.",
    },
    {
        "id": "local",
        "display_name": "Hospital-hosted OpenAI-compatible Model",
        "default_model": "operator-defined",
        "deployment_kind": "self_hosted",
        "credential_required": False,
        "adapter_capabilities": _COMMON_CAPABILITIES,
        "china_scenario": "Preferred option when PHI must remain inside the hospital boundary.",
    },
    {
        "id": "mock",
        "display_name": "Deterministic Mock",
        "default_model": "mock/1.0",
        "deployment_kind": "development_only",
        "credential_required": False,
        "adapter_capabilities": ["contract_testing"],
        "china_scenario": "Testing only; never a clinical model.",
    },
)


def _endpoint_mismatch(provider_id: str, base_url: str) -> bool:
    endpoint = base_url.strip().lower()
    if not endpoint:
        return provider_id != "mock"
    if provider_id == "qwen" and "deepseek.com" in endpoint:
        return True
    if provider_id == "deepseek" and "dashscope.aliyuncs.com" in endpoint:
        return True
    if provider_id == "local" and (
        "deepseek.com" in endpoint or "dashscope.aliyuncs.com" in endpoint
    ):
        return True
    return False


def build_model_catalog(
    *,
    configured_provider: str,
    configured_model: str,
    configured_base_url: str,
    credential_configured: bool,
    data_policy: RuntimeDataPolicy,
    tenant_selection: dict[str, Any] | None = None,
    registered_deployments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operator_provider = normalize_provider_name(configured_provider or "mock")
    deployments = [dict(item) for item in (registered_deployments or [])]
    if not deployments:
        deployments = [{
            "id": operator_provider,
            "provider_id": operator_provider,
            "model": configured_model,
            "is_default": True,
            "tenant_selectable": operator_provider != "mock",
            "credential_configured": credential_configured,
            "endpoint_configuration_valid": not _endpoint_mismatch(
                operator_provider, configured_base_url
            ),
        }]
    selection = dict(tenant_selection or {})
    selection_mode = str(selection.get("mode") or "inherit")
    selected_deployment_id = str(selection.get("deployment_id") or "")
    effective_deployment_id = operator_provider
    effective_provider = operator_provider
    effective_model = configured_model
    selected_deployment = None
    if selection_mode == "pinned" and selected_deployment_id:
        effective_deployment_id = selected_deployment_id
        selected_deployment = next(
            (item for item in deployments if item.get("id") == selected_deployment_id),
            None,
        )
        if selected_deployment is not None:
            effective_provider = normalize_provider_name(
                str(selected_deployment.get("provider_id") or "")
            )
            effective_model = str(selected_deployment.get("model") or "")
        else:
            effective_provider = ""
            effective_model = ""
    active_provider = effective_provider or selected_deployment_id
    models: list[dict[str, Any]] = []

    for spec in MODEL_PROVIDER_SPECS:
        provider_id = spec["id"]
        selected = provider_id == effective_provider
        decision = data_policy.egress_decision(provider_id)
        blockers: list[str] = []
        selected_credential_configured = credential_configured
        selected_endpoint_valid = not _endpoint_mismatch(
            provider_id, configured_base_url
        )
        if selected and selected_deployment is not None:
            selected_credential_configured = bool(
                selected_deployment.get("credential_configured", False)
            )
            selected_endpoint_valid = bool(
                selected_deployment.get("endpoint_configuration_valid", False)
            )
        credential_state: bool | None = (
            selected_credential_configured if selected else None
        )

        if selected and spec["credential_required"] and not selected_credential_configured:
            blockers.append("credential_not_configured")
        if selected and decision["decision"] == "deny":
            blockers.append("egress_policy_denied")
        if selected and not selected_endpoint_valid:
            blockers.append("provider_endpoint_mismatch")

        if not selected:
            status = "available_to_configure"
        elif provider_id == "mock":
            status = "development_only"
        elif blockers:
            status = "blocked"
        else:
            status = "configured_not_live_verified"

        models.append({
            **spec,
            "model": effective_model if selected else spec["default_model"],
            "selected": selected,
            "credential_configured": credential_state,
            "provider_region": decision["provider_region"],
            "tenant_region": decision["tenant_region"],
            "egress_decision": decision["decision"],
            "status": status,
            "blocking_reasons": blockers,
        })

    if active_provider not in {item["id"] for item in MODEL_PROVIDER_SPECS}:
        decision = data_policy.egress_decision(active_provider)
        models.insert(0, {
            "id": active_provider,
            "display_name": f"Unsupported provider: {active_provider}",
            "default_model": configured_model or "operator-defined",
            "model": configured_model or "operator-defined",
            "deployment_kind": "unsupported",
            "credential_required": True,
            "credential_configured": credential_configured,
            "adapter_capabilities": [],
            "china_scenario": "No production runtime adapter is registered for this value.",
            "selected": True,
            "provider_region": decision["provider_region"],
            "tenant_region": decision["tenant_region"],
            "egress_decision": decision["decision"],
            "status": "blocked",
            "blocking_reasons": [
                "tenant_model_deployment_unavailable"
                if selection_mode == "pinned" and selected_deployment is None
                else "unsupported_provider_configuration"
            ],
        })

    return {
        "active_provider": active_provider,
        "active_model": effective_model,
        "operator_default_provider": operator_provider,
        "operator_default_model": configured_model,
        "effective_deployment_id": effective_deployment_id,
        "tenant_selection": {
            "mode": selection_mode if selection_mode in {"inherit", "pinned"} else "inherit",
            "deployment_id": selected_deployment_id or None,
            "version": max(0, int(selection.get("version") or 0)),
        },
        "registered_deployments": deployments,
        "tenant_region": data_policy.region,
        "egress_policy": data_policy.egress_policy,
        "external_llm_allowed": data_policy.allow_external_llm,
        "models": models,
        "readiness_scope": "configuration_and_policy_only",
        "live_health_verified": False,
        "disclaimer": (
            "External provider health, clinical quality, latency and hospital approval "
            "require separate live validation; no credential or endpoint URL is returned."
        ),
    }
