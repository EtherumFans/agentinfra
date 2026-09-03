from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from icoder_runtime.core.llm_gateway import BaseLLMProvider


class _NoNetworkLocalProvider(BaseLLMProvider):
    name = "local"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls += 1
        return {"content": "ok", "provider": "local"}


class _SyntheticCanaryProvider(BaseLLMProvider):
    name = "deepseek"

    def __init__(self) -> None:
        self.calls = 0
        self.messages: list[dict[str, Any]] = []
        self.context: dict[str, Any] = {}

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls += 1
        self.messages = [dict(item) for item in messages]
        self.context = dict(context or {})
        return {
            "content": "ICODER_CANARY_OK",
            "model": "deepseek-test",
            "usage": {"input_tokens": 31, "output_tokens": 4},
            "cost_usd": 0.000006,
        }


async def _register(client, label: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post("/api/auth/register", json={
        "username": f"{label}-{suffix}",
        "email": f"{label}-{suffix}@example.com",
        "password": "password123",
        "full_name": f"{label} Test",
        "organization_name": f"{label} Org {suffix}",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_model_catalog_requires_authentication(client, needs_auth) -> None:
    response = await client.get("/api/v1/model-catalog")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_model_catalog_is_authenticated_truthful_and_secret_free(
    client,
    needs_auth,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    registered = await client.post("/api/auth/register", json={
        "username": f"model-catalog-{suffix}",
        "email": f"model-catalog-{suffix}@example.com",
        "password": "password123",
        "full_name": "Model Catalog Test",
    })
    assert registered.status_code == 201
    token = registered.json()["access_token"]

    response = await client.get(
        "/api/v1/model-catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["readiness_scope"] == "configuration_and_policy_only"
    assert body["live_health_verified"] is False
    assert body["live_canary_policy"]["fixed_synthetic_payload"] is True
    assert body["live_canary_policy"]["patient_data_allowed"] is False
    assert len(body["models"]) >= 5
    assert sum(1 for item in body["models"] if item["selected"]) == 1
    serialized = response.text.lower()
    assert "api_key" not in serialized
    assert "credential_llm" not in serialized
    assert "base_url" not in serialized


@pytest.mark.asyncio
async def test_owner_health_probe_is_no_network_audited_and_tenant_visible(
    client,
    needs_auth,
) -> None:
    from app.database import AsyncSessionLocal
    from app.main import app
    from app.models.audit_log import AuditLog
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider

    owner = await _register(client, "model-health")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    previous_gateway = getattr(app.state, "platform_gateway", None)
    previous_policy = getattr(app.state, "data_policy", None)
    previous_deployments = dict(getattr(app.state, "model_deployments", {}) or {})
    previous_health = getattr(app.state, "model_health", None)
    gateway = LLMGateway(
        data_policy=RuntimeDataPolicy(
            allow_external_llm=False,
            region="cn",
            egress_policy="strict",
        )
    ).register(MockLLMProvider(name="local"), default=True)
    app.state.platform_gateway = gateway
    app.state.data_policy = RuntimeDataPolicy(
        allow_external_llm=False,
        region="cn",
        egress_policy="strict",
    )
    app.state.model_deployments = {
        "local": {
            "id": "local",
            "provider_id": "local",
            "model": "hospital-model-v1",
            "is_default": True,
            "tenant_selectable": True,
            "credential_configured": False,
            "endpoint_configuration_valid": True,
        },
    }
    try:
        selected = await client.put(
            "/api/v1/model-catalog/selection",
            headers=headers,
            json={
                "mode": "pinned",
                "deployment_id": "local",
                "expected_version": 0,
            },
        )
        assert selected.status_code == 200, selected.text
        probed = await client.post(
            "/api/v1/model-catalog/health-probe",
            headers=headers,
            json={"deployment_id": "local"},
        )
        assert probed.status_code == 200, probed.text
        body = probed.json()
        assert body["deployment_id"] == "local"
        assert body["probe_mode"] == "configuration"
        assert body["egress_decision"] == "allow"
        assert body["status"] == "healthy"
        assert body["credential_configured"] is False
        assert "api_key" not in probed.text.lower()
        assert "base_url" not in probed.text.lower()

        catalog = await client.get(
            "/api/v1/model-catalog", headers=headers,
        )
        assert catalog.status_code == 200, catalog.text
        selected = next(item for item in catalog.json()["models"] if item["selected"])
        assert selected["health_status"] == "healthy"
        assert selected["health_checked_at"] == body["checked_at"]
        assert catalog.json()["live_health_verified"] is False

        other = await _register(client, "model-health-other")
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        other_selected = await client.put(
            "/api/v1/model-catalog/selection",
            headers=other_headers,
            json={
                "mode": "pinned",
                "deployment_id": "local",
                "expected_version": 0,
            },
        )
        assert other_selected.status_code == 200, other_selected.text
        other_catalog = await client.get(
            "/api/v1/model-catalog", headers=other_headers,
        )
        other_model = next(
            item for item in other_catalog.json()["models"] if item["selected"]
        )
        assert other_model["health_status"] == "unknown"
        assert other_model["health_checked_at"] is None

        async with AsyncSessionLocal() as db:
            audit = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == owner["current_org_id"],
                        AuditLog.action == "model.health.probe",
                    )
                )
            ).scalar_one()
        assert audit.details["probe_mode"] == "configuration"
        assert audit.details["deployment_id"] == "local"
        audit_text = str(audit.details).lower()
        assert "api_key" not in audit_text
        assert "credential_llm" not in audit_text
        assert "base_url" not in audit_text
    finally:
        app.state.model_deployments = previous_deployments
        if previous_gateway is None:
            app.state._state.pop("platform_gateway", None)
        else:
            app.state.platform_gateway = previous_gateway
        if previous_policy is None:
            app.state._state.pop("data_policy", None)
        else:
            app.state.data_policy = previous_policy
        if previous_health is None:
            app.state._state.pop("model_health", None)
        else:
            app.state.model_health = previous_health


@pytest.mark.asyncio
async def test_live_canary_is_explicit_single_call_budgeted_and_phi_free(
    client,
    needs_auth,
) -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.main import app
    from app.models.audit_log import AuditLog
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import LLMGateway

    owner = await _register(client, "model-canary")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    provider = _SyntheticCanaryProvider()
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    gateway = LLMGateway(data_policy=policy).register(provider, default=True)
    previous_gateway = getattr(app.state, "platform_gateway", None)
    previous_policy = getattr(app.state, "data_policy", None)
    previous_deployments = dict(getattr(app.state, "model_deployments", {}) or {})
    previous_canary = getattr(app.state, "model_live_canary", None)
    previous_enabled = settings.ICODER_MODEL_LIVE_CANARY_ENABLED
    app.state.platform_gateway = gateway
    app.state.data_policy = policy
    app.state.model_deployments = {
        "deepseek": {
            "id": "deepseek",
            "provider_id": "deepseek",
            "model": "deepseek-test",
            "is_default": True,
            "tenant_selectable": True,
            "credential_configured": True,
            "endpoint_configuration_valid": True,
        },
    }
    settings.ICODER_MODEL_LIVE_CANARY_ENABLED = True
    try:
        rejected_free_text = await client.post(
            "/api/v1/model-catalog/live-canary",
            headers=headers,
            json={
                "deployment_id": "deepseek",
                "acknowledge_external_call": True,
                "purpose": "connectivity_only_no_patient_data",
                "max_cost_cny": 0.01,
                "prompt": "must never be accepted",
            },
        )
        assert rejected_free_text.status_code == 422
        assert provider.calls == 0

        response = await client.post(
            "/api/v1/model-catalog/live-canary",
            headers=headers,
            json={
                "deployment_id": "deepseek",
                "acknowledge_external_call": True,
                "purpose": "connectivity_only_no_patient_data",
                "max_cost_cny": 0.01,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "reachable"
        assert body["probe_mode"] == "external_connectivity_canary"
        assert body["synthetic_payload"] is True
        assert body["patient_data_sent"] is False
        assert body["expected_token_matched"] is True
        assert body["cost"] == {
            "amount": 0.000006,
            "currency": "CNY",
            "billing_authoritative": False,
            "source": "provider_usage_pricing_estimate",
        }
        assert provider.calls == 1
        assert provider.context == {
            "max_tokens": 8,
            "temperature": 0.0,
            "timeout_seconds": 15.0,
            "max_attempts": 1,
        }
        assert all("患者" not in item["content"] for item in provider.messages)
        assert "ICODER_CANARY_OK" not in response.text
        assert "api_key" not in response.text.lower()
        assert "base_url" not in response.text.lower()

        repeated = await client.post(
            "/api/v1/model-catalog/live-canary",
            headers=headers,
            json={
                "deployment_id": "deepseek",
                "acknowledge_external_call": True,
                "purpose": "connectivity_only_no_patient_data",
                "max_cost_cny": 0.01,
            },
        )
        assert repeated.status_code == 429
        assert repeated.headers["retry-after"] == "300"
        assert provider.calls == 1

        catalog = await client.get("/api/v1/model-catalog", headers=headers)
        canaried = next(
            item for item in catalog.json()["models"] if item["id"] == "deepseek"
        )
        assert canaried["canary_status"] == "reachable"
        assert canaried["canary_scope"] == "connectivity_only_no_patient_data"
        deployment = next(
            item for item in catalog.json()["registered_deployments"]
            if item["id"] == "deepseek"
        )
        assert deployment["canary_status"] == "reachable"
        assert catalog.json()["live_health_verified"] is False

        other = await _register(client, "model-canary-other")
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        other_selected = await client.put(
            "/api/v1/model-catalog/selection",
            headers=other_headers,
            json={
                "mode": "pinned",
                "deployment_id": "deepseek",
                "expected_version": 0,
            },
        )
        assert other_selected.status_code == 200, other_selected.text
        other_catalog = await client.get(
            "/api/v1/model-catalog", headers=other_headers,
        )
        other_model = next(
            item for item in other_catalog.json()["models"] if item["selected"]
        )
        assert other_model["canary_status"] == "not_run"
        assert other_model["canary_checked_at"] is None

        async with AsyncSessionLocal() as db:
            audits = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == owner["current_org_id"],
                        AuditLog.action.in_([
                            "model.live_canary.started",
                            "model.live_canary.completed",
                        ]),
                    ).order_by(AuditLog.created_at)
                )
            ).scalars().all()
        assert [item.action for item in audits] == [
            "model.live_canary.started",
            "model.live_canary.completed",
        ]
        audit_text = str([item.details for item in audits]).lower()
        assert "icoder_canary_ok" not in audit_text
        assert "api_key" not in audit_text
        assert "base_url" not in audit_text
        assert audits[1].details["patient_data_sent"] is False
    finally:
        settings.ICODER_MODEL_LIVE_CANARY_ENABLED = previous_enabled
        app.state.model_deployments = previous_deployments
        if previous_gateway is None:
            app.state._state.pop("platform_gateway", None)
        else:
            app.state.platform_gateway = previous_gateway
        if previous_policy is None:
            app.state._state.pop("data_policy", None)
        else:
            app.state.data_policy = previous_policy
        if previous_canary is None:
            app.state._state.pop("model_live_canary", None)
        else:
            app.state.model_live_canary = previous_canary


@pytest.mark.asyncio
async def test_live_canary_disabled_or_egress_denied_never_calls_provider(
    client,
    needs_auth,
) -> None:
    from app.config import settings
    from app.main import app
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import LLMGateway

    owner = await _register(client, "model-canary-denied")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    provider = _SyntheticCanaryProvider()
    denied_policy = RuntimeDataPolicy(
        allow_external_llm=False,
        region="cn",
        egress_policy="strict",
    )
    previous_gateway = getattr(app.state, "platform_gateway", None)
    previous_policy = getattr(app.state, "data_policy", None)
    previous_deployments = dict(getattr(app.state, "model_deployments", {}) or {})
    previous_enabled = settings.ICODER_MODEL_LIVE_CANARY_ENABLED
    app.state.platform_gateway = LLMGateway(data_policy=denied_policy).register(
        provider, default=True,
    )
    app.state.data_policy = denied_policy
    app.state.model_deployments = {
        "deepseek": {
            "id": "deepseek", "provider_id": "deepseek",
            "model": "deepseek-test", "credential_configured": True,
        },
    }
    payload = {
        "deployment_id": "deepseek",
        "acknowledge_external_call": True,
        "purpose": "connectivity_only_no_patient_data",
        "max_cost_cny": 0.01,
    }
    try:
        settings.ICODER_MODEL_LIVE_CANARY_ENABLED = False
        disabled = await client.post(
            "/api/v1/model-catalog/live-canary", headers=headers, json=payload,
        )
        assert disabled.status_code == 403
        assert disabled.json()["detail"]["code"] == "MODEL_LIVE_CANARY_DISABLED"

        settings.ICODER_MODEL_LIVE_CANARY_ENABLED = True
        denied = await client.post(
            "/api/v1/model-catalog/live-canary", headers=headers, json=payload,
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "MODEL_LIVE_CANARY_EGRESS_DENIED"
        assert provider.calls == 0
    finally:
        settings.ICODER_MODEL_LIVE_CANARY_ENABLED = previous_enabled
        app.state.model_deployments = previous_deployments
        if previous_gateway is None:
            app.state._state.pop("platform_gateway", None)
        else:
            app.state.platform_gateway = previous_gateway
        if previous_policy is None:
            app.state._state.pop("data_policy", None)
        else:
            app.state.data_policy = previous_policy


@pytest.mark.asyncio
async def test_owner_can_pin_registered_local_deployment_with_versioned_audit(
    client,
    needs_auth,
) -> None:
    from app.database import AsyncSessionLocal
    from app.main import app
    from app.models.audit_log import AuditLog
    from app.models.organization import OrganizationMember, OrgRole
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider
    from icoder_runtime.core.llm_provider_factory import create_primary_llm_provider
    from app.services.tenant_model_routing import (
        bind_request_tenant,
        reset_request_tenant,
        resolve_tenant_model_route,
    )

    owner = await _register(client, "model-owner")
    other = await _register(client, "model-other")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    previous_gateway = getattr(app.state, "platform_gateway", None)
    previous_policy = getattr(app.state, "data_policy", None)
    previous_deployments = dict(
        getattr(app.state, "model_deployments", {}) or {}
    )
    gateway = LLMGateway(
        data_policy=RuntimeDataPolicy(
            allow_external_llm=False,
            region="cn",
            egress_policy="strict",
        )
    ).register(MockLLMProvider(), default=True)
    app.state.platform_gateway = gateway
    app.state.data_policy = RuntimeDataPolicy(
        allow_external_llm=False,
        region="cn",
        egress_policy="strict",
    )
    local = create_primary_llm_provider(
        provider_name="local",
        api_key="",
        base_url="http://model-gateway.hospital.local/v1",
        model="hospital-model-v1",
    )
    gateway.register(local)
    app.state.model_deployments = {
        **previous_deployments,
        "local": {
            "id": "local",
            "provider_id": "local",
            "model": "hospital-model-v1",
            "is_default": False,
                "tenant_selectable": True,
                "credential_configured": False,
                "endpoint_configuration_valid": True,
        },
    }
    try:
        selected = await client.put(
            "/api/v1/model-catalog/selection",
            headers=headers,
            json={
                "mode": "pinned",
                "deployment_id": "local",
                "expected_version": 0,
            },
        )
        assert selected.status_code == 200, selected.text
        assert selected.headers["cache-control"] == "no-store"
        assert selected.json() == {
            "mode": "pinned",
            "deployment_id": "local",
            "version": 1,
        }

        stale = await client.put(
            "/api/v1/model-catalog/selection",
            headers=headers,
            json={"mode": "inherit", "expected_version": 0},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "MODEL_SELECTION_VERSION_CONFLICT"

        catalog = await client.get("/api/v1/model-catalog", headers=headers)
        assert catalog.status_code == 200
        body = catalog.json()
        assert body["active_provider"] == "local"
        assert body["active_model"] == "hospital-model-v1"
        assert body["effective_deployment_id"] == "local"
        assert body["tenant_selection"] == {
            "mode": "pinned",
            "deployment_id": "local",
            "version": 1,
        }
        assert body["selection_editable"] is True

        routed_provider = _NoNetworkLocalProvider()
        runtime_gateway = LLMGateway(
            data_policy=app.state.data_policy,
            tenant_provider_resolver=resolve_tenant_model_route,
        ).register(MockLLMProvider(), default=True)
        runtime_gateway.register(routed_provider)
        routing_token = bind_request_tenant(owner["current_org_id"])
        try:
            routed = await runtime_gateway.generate(
                [{"role": "user", "content": "contract-only"}],
            )
        finally:
            reset_request_tenant(routing_token)
        assert routed_provider.calls == 1
        assert routed["provider"] == "local"
        assert routed["model_routing"]["deployment_id"] == "local"
        assert routed["model_routing"]["selection_version"] == 1

        other_catalog = await client.get(
            "/api/v1/model-catalog", headers=other_headers,
        )
        assert other_catalog.status_code == 200
        assert other_catalog.json()["tenant_selection"]["mode"] == "inherit"

        reserved = await client.patch(
            f"/api/organizations/{owner['current_org_id']}",
            headers=headers,
            json={"settings": {"_model_routing": {"mode": "inherit"}}},
        )
        assert reserved.status_code == 403

        async with AsyncSessionLocal() as db:
            audits = (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.organization_id == owner["current_org_id"],
                        AuditLog.action == "model.selection.update",
                    )
                )
            ).scalars().all()
        assert len(audits) == 1
        assert audits[0].details["model_deployment_id"] == "local"
        assert "api_key" not in str(audits[0].details).lower()

        async with AsyncSessionLocal() as db:
            membership = (
                await db.execute(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == owner["current_org_id"],
                        OrganizationMember.user_id == owner["user"]["id"],
                    )
                )
            ).scalar_one()
            membership.role = OrgRole.VIEWER
            await db.commit()
        denied = await client.put(
            "/api/v1/model-catalog/selection",
            headers=headers,
            json={"mode": "inherit", "expected_version": 1},
        )
        assert denied.status_code == 403
    finally:
        app.state.model_deployments = previous_deployments
        if previous_gateway is None:
            app.state._state.pop("platform_gateway", None)
        else:
            app.state.platform_gateway = previous_gateway
        if previous_policy is None:
            app.state._state.pop("data_policy", None)
        else:
            app.state.data_policy = previous_policy
