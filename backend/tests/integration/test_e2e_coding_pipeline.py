"""E2E Integration Tests for iCoDer — runs against live dev server on port 8765.

Prerequisites:
    python -m uvicorn app.main:app --port 8765
    python -c "from app.seed import seed; import asyncio; asyncio.run(seed())"

Phase 3-D0 Task 3 (2026-07-06): opted-in via ``infra`` marker. Default
test sweep excludes this file (no live server in CI). Run explicitly:
``pytest -m infra`` after starting uvicorn on :8765.
"""

import os
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient

# Opt-in marker — excluded from default sweep via pytest.ini addopts.
pytestmark = pytest.mark.infra

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8765")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(base_url=BASE_URL, timeout=60) as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    resp = await client.post("/api/auth/login", json={
        "username": "admin", "password": "admin123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_e2e_full_flow(client, auth_headers):
    """Complete flow: encounter → review pipeline → verify output."""
    # Create encounter
    enc_resp = await client.post("/api/encounters/text", json={
        "department": "orthopedics",
        "admission_reason": "back pain for 4 months",
        "raw_text": (
            "Patient with low back pain for 4 months. MRI shows T7/T9/T12/L2 "
            "compression fractures. Diagnosed with osteoporosis and hypertension. "
            "Underwent percutaneous kyphoplasty. Post-op pain relieved."
        ),
    }, headers=auth_headers)
    assert enc_resp.status_code == 201, f"Encounter failed: {enc_resp.text}"
    encounter_id = enc_resp.json()["encounter_id"]
    assert encounter_id.startswith("ENC-")

    # Run review pipeline (async)
    rev_resp = await client.post("/api/reviews", json={
        "encounter_id": encounter_id,
    }, headers=auth_headers, params={"async": "true"})
    assert rev_resp.status_code == 201, f"Review failed: {rev_resp.text}"
    task_id = rev_resp.json()["task_id"]
    assert task_id is not None

    # Poll for completion
    for _ in range(12):
        await asyncio.sleep(5)
        task_resp = await client.get(f"/api/reviews/tasks/{task_id}", headers=auth_headers)
        if task_resp.status_code == 200:
            task = task_resp.json()
            if task["status"] == "completed":
                assert task.get("progress") == 100
                assert len(task.get("steps", [])) >= 5
                break
            elif task["status"] == "failed":
                pytest.fail(f"Pipeline failed: {task.get('error')}")
    else:
        pytest.fail("Pipeline did not complete within 60s")


@pytest.mark.asyncio
async def test_tool_registry(client, auth_headers):
    """Verify 17 tools with contracts."""
    resp = await client.get("/api/tools", headers=auth_headers)
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    assert len(tools) == 17
    assert len([t for t in tools if t["tier"] == 1]) == 7
    assert len([t for t in tools if t["tier"] == 2]) == 10


@pytest.mark.asyncio
async def test_agent_tool_native_config(client, auth_headers):
    """Verify agent creation with tool-native config persists."""
    resp = await client.post("/rest/v1/agent_definitions", json={
        "name": "E2E-ToolAgent",
        "system_prompt": "test",
        "config": {
            "routing_strategy": "tool_native",
            "tools": {"enabled": ["extract_evidence"], "tier1_enforce": True},
        },
    }, headers=auth_headers)
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config["routing_strategy"] == "tool_native"


@pytest.mark.asyncio
async def test_key_endpoints(client, auth_headers):
    """Verify all key API endpoints return 200."""
    endpoints = [
        "/rest/v1/agent_definitions", "/rest/v1/agent_definitions/templates", "/api/tools",
        "/api/tools/categories", "/api/encounters",
        "/api/billing/balance", "/api/team/members",
    ]
    for ep in endpoints:
        resp = await client.get(ep, headers=auth_headers)
        assert resp.status_code == 200, f"{ep}: {resp.status_code}"
