# Auth API Integration Tests
import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "iCoDer Medical Coding Agent"


@pytest.mark.asyncio
async def test_register(client):
    response = await client.post("/api/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "password123",
        "full_name": "New User",
        "role": "coder",
        "department": "内科",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "newuser"


@pytest.mark.asyncio
async def test_register_duplicate(client):
    # First registration
    await client.post("/api/auth/register", json={
        "username": "dupuser",
        "email": "dup@example.com",
        "password": "password123",
        "full_name": "Dup User",
    })
    # Duplicate
    response = await client.post("/api/auth/register", json={
        "username": "dupuser",
        "email": "dup2@example.com",
        "password": "password123",
        "full_name": "Dup User 2",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client):
    # Register first
    await client.post("/api/auth/register", json={
        "username": "loginuser",
        "email": "login@example.com",
        "password": "loginpass123",
        "full_name": "Login User",
    })
    response = await client.post("/api/auth/login", json={
        "username": "loginuser",
        "password": "loginpass123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_failure(client):
    response = await client.post("/api/auth/login", json={
        "username": "nonexistent",
        "password": "wrong",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client):
    response = await client.get("/api/encounters")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(auth_client):
    response = await auth_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
