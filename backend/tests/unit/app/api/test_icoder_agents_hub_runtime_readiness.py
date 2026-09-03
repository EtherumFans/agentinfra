"""Runtime-readiness projection tests for public and tenant Hub boundaries."""

from __future__ import annotations

from app.api import icoder_agents_hub as hub


def _card(target: str, *, llm_required: bool) -> dict[str, object]:
    return {
        "execution_target": target,
        "runtime_readiness": {
            "structural_status": "ready",
            "configuration_status": "configured_not_live_verified",
            "run_action_enabled": True,
            "reason": "must_be_replaced",
            "external_llm_required": llm_required,
            "live_health_verified": True,
            "semantic_validation_status": "not_verified",
            "production_approval_status": "not_approved",
        },
    }


def test_public_hub_never_projects_operator_or_tenant_runtime_state() -> None:
    cards = [
        _card("icoder.pure-llm.v1", llm_required=True),
        _card("icoder.rule-engine.v1", llm_required=False),
    ]

    hub._attach_public_runtime_readiness(cards)

    for card in cards:
        readiness = card["runtime_readiness"]
        assert isinstance(readiness, dict)
        assert readiness["configuration_status"] == "not_checked"
        assert readiness["run_action_enabled"] is False
        assert readiness["reason"] == (
            "tenant_runtime_readiness_requires_authentication"
        )
        assert readiness["live_health_verified"] is False
        assert "api_key" not in readiness
        assert "endpoint" not in readiness


def test_tenant_configuration_reason_is_stable_and_secret_free() -> None:
    cases = [
        (None, "tenant_model_deployment_unavailable"),
        ({"status": "development_only"}, "mock_provider"),
        (
            {"status": "blocked", "blocking_reasons": ["credential_not_configured"]},
            "credential_not_configured",
        ),
        (
            {"status": "blocked", "blocking_reasons": ["egress_policy_denied"]},
            "external_llm_egress_denied",
        ),
        (
            {
                "status": "blocked",
                "blocking_reasons": ["unknown"],
                "api_key": "must-not-be-reflected",
                "base_url": "https://secret.internal",
            },
            "tenant_model_configuration_unavailable",
        ),
    ]

    for model, expected in cases:
        assert hub._tenant_configuration_reason(model) == expected

