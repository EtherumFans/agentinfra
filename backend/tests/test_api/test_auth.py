# Auth API Integration Tests
"""Phase 3-D0 Task 3 — fixed test_register isolation flake.

Root cause: tests used fixed emails/usernames ("new@example.com" /
"newuser") and the session-scoped DB only drops tables at the very
end. A re-run of test_register hits 400 (user already exists) instead
of 201 → flake. Fix: per-invocation unique suffix via uuid4.
"""
import uuid

import pytest


def _short_uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "iCoDer Medical Coding Agent"


@pytest.mark.asyncio
async def test_register(client):
    uid = _short_uid()
    response = await client.post("/api/auth/register", json={
        "username": f"newuser-{uid}",
        "email": f"new-{uid}@example.com",
        "password": "password123",
        "full_name": "New User",
        "role": "coder",
        "department": "内科",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == f"newuser-{uid}"


@pytest.mark.asyncio
async def test_register_duplicate(client):
    uid = _short_uid()
    username = f"dupuser-{uid}"
    # First registration
    await client.post("/api/auth/register", json={
        "username": username,
        "email": f"dup-{uid}@example.com",
        "password": "password123",
        "full_name": "Dup User",
    })
    # Duplicate (same username — must 400)
    response = await client.post("/api/auth/register", json={
        "username": username,
        "email": f"dup2-{uid}@example.com",
        "password": "password123",
        "full_name": "Dup User 2",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    uid = _short_uid()
    username = f"loginuser-{uid}"
    # Register first
    await client.post("/api/auth/register", json={
        "username": username,
        "email": f"login-{uid}@example.com",
        "password": "loginpass123",
        "full_name": "Login User",
    })
    response = await client.post("/api/auth/login", json={
        "username": username,
        "password": "loginpass123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_failure(client):
    uid = _short_uid()
    response = await client.post("/api/auth/login", json={
        "username": f"nonexistent-{uid}",
        "password": "wrong",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client, needs_auth):
    response = await client.get("/api/encounters")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(auth_client):
    response = await auth_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
