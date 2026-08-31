from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_process_metrics_requires_authentication(client, needs_auth):
    response = await client.get("/api/metrics")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_process_metrics_rejects_tenant_coder(client, needs_auth):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    registered = await client.post("/api/auth/register", json={
        "username": f"metrics-{suffix}",
        "email": f"metrics-{suffix}@example.com",
        "password": "password123",
        "full_name": "Metrics Tenant User",
    })
    assert registered.status_code == 201
    token = registered.json()["access_token"]

    response = await client.get(
        "/api/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_process_metrics_accepts_rotatable_monitoring_token(
    client,
    needs_auth,
    monkeypatch,
):
    token = "monitoring-token-that-is-longer-than-32-characters"
    monkeypatch.setenv("ICODER_METRICS_BEARER_TOKEN", token)
    response = await client.get(
        "/api/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["scope"] == "single_api_process"
    clinical_shadow = response.json()["clinical_shadow"]
    assert clinical_shadow["scope"] == "single_api_or_worker_process"
    assert clinical_shadow["patient_labels_present"] is False
    assert clinical_shadow["tenant_labels_present"] is False
    assert clinical_shadow["job_labels_present"] is False
