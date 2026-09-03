from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_environment_catalog_and_regions_are_real_declarative_views(client) -> None:
    environments = await client.get("/api/platform/environments")
    assert environments.status_code == 200
    body = environments.json()
    assert body["source"] == "deploy/cloud/regions.yaml"
    assert {item["code"] for item in body["environments"]} == {"eu", "us", "cn"}
    assert all(item["runtime_state"] == "declared_not_provisioned" for item in body["environments"])

    regions = await client.get("/api/platform/regions")
    assert regions.status_code == 200
    region_body = regions.json()
    assert len(region_body["regions"]) == 6
    china = [item for item in region_body["regions"] if item["environment_code"] == "cn"]
    assert {item["code"] for item in china} == {"cn-hangzhou", "cn-beijing"}
    assert "个人信息保护法" in china[0]["compliance"]


async def test_environment_create_is_safe_dry_run_only(client) -> None:
    response = await client.post(
        "/api/platform/environments",
        json={
            "environment_code": "cn",
            "region_code": "cn-hangzhou",
            "tenant_id": "org_default1",
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["provisioned"] is False
    assert body["external_approval_required"] is True
    assert "validate_tenant_data_residency" in body["steps"]

    blocked = await client.post(
        "/api/platform/environments",
        json={
            "environment_code": "cn",
            "region_code": "cn-hangzhou",
            "dry_run": False,
        },
    )
    assert blocked.status_code == 409


async def test_current_tenant_projects_organization_without_claiming_cloud(client) -> None:
    current = await client.get("/api/tenants/current")
    assert current.status_code == 200
    body = current.json()
    assert body["id"] == "org_default1"
    assert body["country"] == "CN"
    assert body["environment_assignments"] == []

    environments = await client.get("/api/tenants/org_default1/environments")
    assert environments.status_code == 200
    assert environments.json() == {
        "tenant_id": "org_default1",
        "environment_assignments": [],
        "environment_provisioned": False,
        "deployment_mode": "local_or_pending",
    }


async def test_tenant_environment_read_is_tenant_scoped(client) -> None:
    response = await client.get("/api/tenants/other-org/environments")
    assert response.status_code == 403


async def test_tenant_create_uses_organization_master_and_validates_environment(client) -> None:
    created = await client.post(
        "/api/tenants",
        json={
            "name": "China Deployment Simulation Tenant",
            "country": "cn",
            "use_cases": ["medical-coding", "cdi"],
            "features_enabled": ["agent-hub"],
            "environment_assignments": ["cn"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["country"] == "CN"
    assert body["environment_assignments"] == ["cn"]
    assert body["verified"] is False

    invalid = await client.post(
        "/api/tenants",
        json={
            "name": "Invalid Deployment Simulation Tenant",
            "environment_assignments": ["moon"],
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["unknown"] == ["moon"]
