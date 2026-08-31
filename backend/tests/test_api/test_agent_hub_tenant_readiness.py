from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from sqlalchemy import select


async def _register(client, label: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post(
        "/api/auth/register",
        json={
            "username": f"{label}-{suffix}",
            "email": f"{label}-{suffix}@example.com",
            "password": "password123",
            "full_name": f"{label} Test",
            "organization_name": f"{label} Org {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _pin_org(organization_id: str, deployment_id: str, version: int) -> None:
    from app.database import AsyncSessionLocal
    from app.models.organization import Organization
    from app.services.tenant_model_routing import update_selection_settings

    async with AsyncSessionLocal() as db:
        org = (
            await db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
        ).scalar_one()
        org.settings = update_selection_settings(
            org.settings,
            mode="pinned",
            deployment_id=deployment_id,
            version=version,
        )
        await db.commit()


async def _record_canary(
    registered: dict,
    *,
    deployment_id: str,
    created_at: datetime,
    valid: bool,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    details = {
        "deployment_id": deployment_id,
        "status": "reachable" if valid else "failed",
        "reason_code": "ok" if valid else "provider_error",
        "expected_token_matched": valid,
        "patient_data_sent": False,
    }
    async with AsyncSessionLocal() as db:
        db.add(
            AuditLog(
                organization_id=registered["current_org_id"],
                user_id=registered["user"]["id"],
                username=registered["user"]["username"],
                action="model.live_canary.completed",
                resource_type="model_deployment",
                resource_id=deployment_id,
                details=details,
                status="success" if valid else "failure",
                created_at=created_at.replace(tzinfo=None),
            )
        )
        await db.commit()


def _cards_by_llm_requirement(body: dict) -> tuple[list[dict], list[dict]]:
    local = [
        item for item in body["agents"]
        if not item["runtime_readiness"]["llm_required"]
    ]
    llm = [
        item for item in body["agents"]
        if item["runtime_readiness"]["llm_required"]
    ]
    assert [item["agent_id"] for item in local] == [
        "claim-check",
        "clinical-education",
        "clinical-guidelines",
        "code-validation-agent",
        "compliance-guardrail-agent",
        "denial-appeals",
        "diagnosis-extractor",
        "discharge-edu",
        "discharge-summary-structuring",
        "drg-analyzer",
        "evidence-extractor",
        "evidence-ranker",
        "icd10-navigator",
        "icu-summary",
        "med-reconciliation",
        "note-completeness-agent",
        "nursing-handoff",
        "principal-diagnosis-review",
        "prior-auth",
        "procedure-extractor",
        "referral-gen",
        "rule-explainer",
        "surgical-registry",
        "triage",
    ]
    assert [item["agent_id"] for item in llm] == [
        "clinical-documentation-improvement-agent",
        "medical-coding-agent",
    ]
    return local, llm


@pytest.fixture
def configured_deepseek_runtime(monkeypatch):
    from app.main import app
    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    previous_policy = getattr(app.state, "data_policy", None)
    previous_deployments = getattr(app.state, "model_deployments", None)
    previous_health = getattr(app.state, "model_health", None)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "")
    app.state.data_policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    app.state.model_deployments = {
        deployment_id: {
            "id": deployment_id,
            "provider_id": deployment_id,
            "model": f"{deployment_id}-test",
            "is_default": deployment_id == "deepseek",
            "tenant_selectable": True,
            "credential_configured": True,
            "endpoint_configuration_valid": True,
        }
        for deployment_id in ("deepseek", "qwen")
    }
    app.state.model_health = {}
    try:
        yield
    finally:
        if previous_policy is None:
            app.state._state.pop("data_policy", None)
        else:
            app.state.data_policy = previous_policy
        if previous_deployments is None:
            app.state._state.pop("model_deployments", None)
        else:
            app.state.model_deployments = previous_deployments
        if previous_health is None:
            app.state._state.pop("model_health", None)
        else:
            app.state.model_health = previous_health


@pytest.mark.asyncio
async def test_tenant_readiness_requires_authentication(client, needs_auth) -> None:
    response = await client.get("/api/icoder/agents/hub/readiness")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mock_tenant_readiness_is_secret_free_and_fail_closed(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    registered = await _register(client, "hub-readiness-mock")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    monkeypatch.setenv(
        "ICODER_CREDENTIAL_LLM",
        "test-only-secret-that-must-never-appear",
    )
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["total"] == len(body["agents"]) == 26
    local, llm = _cards_by_llm_requirement(body)
    assert all(
        item["runtime_readiness"]["configuration_status"] == "local_ready"
        for item in local
    )
    assert all(item["runtime_readiness"]["run_action_enabled"] for item in local)
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "verified"
        for item in local
    )
    assert all(
        item["runtime_readiness"]["live_health_verified"] is True
        for item in local
    )
    assert all(
        item["runtime_readiness"]["reason"] == "local_runtime_health_verified"
        for item in local
    )
    assert all(
        item["runtime_readiness"]["configuration_status"] == "unavailable"
        for item in llm
    )
    assert all(
        item["runtime_readiness"]["reason"] == "mock_provider"
        for item in llm
    )
    assert all(not item["runtime_readiness"]["run_action_enabled"] for item in llm)
    assert all(not item["runtime_readiness"]["live_health_verified"] for item in llm)
    assert "test-only-secret-that-must-never-appear" not in response.text
    assert "api_key" not in response.text.lower()
    assert "base_url" not in response.text.lower()


@pytest.mark.asyncio
async def test_local_catalog_health_failure_disables_code_validation_run(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from icoder_runtime.backends.contracts import ProviderHealth
    from icoder_runtime.backends.registry import get_default_registry

    registered = await _register(client, "hub-local-health")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    provider = get_default_registry().get("icoder.governed-code-validation.v1")

    async def down():
        return ProviderHealth(
            state="down",
            details={"error": "catalog_health_failed:IntegrityError"},
        )

    monkeypatch.setattr(provider, "health", down)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "")
    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    items = {item["agent_id"]: item for item in response.json()["agents"]}
    code_validation = items["code-validation-agent"]
    readiness = code_validation["runtime_readiness"]
    assert readiness["configuration_status"] == "unavailable"
    assert readiness["run_action_enabled"] is False
    assert readiness["reason"] == "local_runtime_health_failed"
    assert readiness["connectivity_status"] == "failed"
    assert readiness["live_health_verified"] is False
    assert code_validation["evidence"]["configuration_probe_status"] == "down"
    assert items["compliance-guardrail-agent"]["runtime_readiness"][
        "run_action_enabled"
    ] is True


@pytest.mark.asyncio
async def test_local_index_health_failure_disables_only_icd10_navigator_run(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from icoder_runtime.backends.contracts import ProviderHealth
    from icoder_runtime.backends.registry import get_default_registry

    registered = await _register(client, "hub-local-index-health")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    provider = get_default_registry().get("icoder.governed-icd-navigator.v1")

    async def down():
        return ProviderHealth(
            state="down",
            details={"error": "index_health_failed:IntegrityError"},
        )

    monkeypatch.setattr(provider, "health", down)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "")
    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    items = {item["agent_id"]: item for item in response.json()["agents"]}
    navigator = items["icd10-navigator"]
    readiness = navigator["runtime_readiness"]
    assert readiness["configuration_status"] == "unavailable"
    assert readiness["run_action_enabled"] is False
    assert readiness["reason"] == "local_runtime_health_failed"
    assert readiness["connectivity_status"] == "failed"
    assert readiness["live_health_verified"] is False
    assert navigator["evidence"]["configuration_probe_status"] == "down"
    assert items["code-validation-agent"]["runtime_readiness"][
        "run_action_enabled"
    ] is True


@pytest.mark.asyncio
async def test_local_evidence_policy_health_failure_disables_only_ranker_run(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from icoder_runtime.backends.contracts import ProviderHealth
    from icoder_runtime.backends.registry import get_default_registry

    registered = await _register(client, "hub-local-evidence-health")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    provider = get_default_registry().get("icoder.governed-evidence-ranker.v1")

    async def down():
        return ProviderHealth(
            state="down",
            details={"error": "evidence_policy_health_failed:RuntimeError"},
        )

    monkeypatch.setattr(provider, "health", down)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "")
    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    items = {item["agent_id"]: item for item in response.json()["agents"]}
    ranker = items["evidence-ranker"]
    readiness = ranker["runtime_readiness"]
    assert readiness["configuration_status"] == "unavailable"
    assert readiness["run_action_enabled"] is False
    assert readiness["reason"] == "local_runtime_health_failed"
    assert readiness["connectivity_status"] == "failed"
    assert readiness["live_health_verified"] is False
    assert ranker["evidence"]["configuration_probe_status"] == "down"
    assert items["icd10-navigator"]["runtime_readiness"][
        "run_action_enabled"
    ] is True


@pytest.mark.asyncio
async def test_configured_tenant_can_run_without_claiming_live_verification(
    client,
    needs_auth,
    configured_deepseek_runtime,
) -> None:
    registered = await _register(client, "hub-readiness-configured")
    await _pin_org(registered["current_org_id"], "deepseek", 1)
    headers = {"Authorization": f"Bearer {registered['access_token']}"}

    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    _, llm = _cards_by_llm_requirement(response.json())
    assert all(
        item["runtime_readiness"]["configuration_status"] == "configured"
        for item in llm
    )
    assert all(item["runtime_readiness"]["run_action_enabled"] for item in llm)
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "not_run"
        for item in llm
    )
    assert all(not item["runtime_readiness"]["live_health_verified"] for item in llm)
    assert all(item["evidence"]["deployment_id"] == "deepseek" for item in llm)
    assert all(item["evidence"]["selection_mode"] == "pinned" for item in llm)


@pytest.mark.asyncio
async def test_fresh_canary_is_tenant_and_selected_deployment_bound(
    client,
    needs_auth,
    configured_deepseek_runtime,
) -> None:
    owner = await _register(client, "hub-readiness-canary-owner")
    other = await _register(client, "hub-readiness-canary-other")
    await _pin_org(owner["current_org_id"], "deepseek", 1)
    await _pin_org(other["current_org_id"], "deepseek", 1)
    await _record_canary(
        owner,
        deployment_id="deepseek",
        created_at=datetime.now(UTC),
        valid=True,
    )

    owner_response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    other_response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )

    assert owner_response.status_code == other_response.status_code == 200
    _, owner_llm = _cards_by_llm_requirement(owner_response.json())
    _, other_llm = _cards_by_llm_requirement(other_response.json())
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "verified"
        for item in owner_llm
    )
    assert all(item["runtime_readiness"]["live_health_verified"] for item in owner_llm)
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "not_run"
        for item in other_llm
    )
    assert all(not item["runtime_readiness"]["live_health_verified"] for item in other_llm)

    await _pin_org(owner["current_org_id"], "qwen", 2)
    switched = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    _, switched_llm = _cards_by_llm_requirement(switched.json())
    assert all(item["evidence"]["deployment_id"] == "qwen" for item in switched_llm)
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "not_run"
        for item in switched_llm
    )
    assert all(not item["runtime_readiness"]["live_health_verified"] for item in switched_llm)


@pytest.mark.asyncio
async def test_expired_canary_drops_live_claim_but_keeps_configured_action(
    client,
    needs_auth,
    configured_deepseek_runtime,
) -> None:
    from app.config import settings

    registered = await _register(client, "hub-readiness-expired")
    await _pin_org(registered["current_org_id"], "deepseek", 1)
    await _record_canary(
        registered,
        deployment_id="deepseek",
        created_at=datetime.now(UTC) - timedelta(
            seconds=settings.ICODER_MODEL_LIVE_CANARY_READINESS_TTL_SECONDS + 1
        ),
        valid=True,
    )

    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    _, llm = _cards_by_llm_requirement(response.json())
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "expired"
        for item in llm
    )
    assert all(not item["runtime_readiness"]["live_health_verified"] for item in llm)
    assert all(item["runtime_readiness"]["run_action_enabled"] for item in llm)


@pytest.mark.asyncio
async def test_failed_canary_disables_llm_actions(
    client,
    needs_auth,
    configured_deepseek_runtime,
) -> None:
    registered = await _register(client, "hub-readiness-failed")
    await _pin_org(registered["current_org_id"], "deepseek", 1)
    await _record_canary(
        registered,
        deployment_id="deepseek",
        created_at=datetime.now(UTC),
        valid=False,
    )

    response = await client.get(
        "/api/icoder/agents/hub/readiness",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    local, llm = _cards_by_llm_requirement(response.json())
    assert local[0]["runtime_readiness"]["run_action_enabled"] is True
    assert all(
        item["runtime_readiness"]["connectivity_status"] == "failed"
        for item in llm
    )
    assert all(not item["runtime_readiness"]["run_action_enabled"] for item in llm)
    assert all(
        item["runtime_readiness"]["reason"] == "tenant_model_connectivity_failed"
        for item in llm
    )
