"""Test OAuth 2.0 endpoints"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_token_endpoint_missing_grant_type(auth_client: AsyncClient):
    resp = await auth_client.post("/api/oauth/token", data={
        "client_id": "test", "client_secret": "test"
    })
    assert resp.status_code == 422  # missing grant_type


@pytest.mark.asyncio
async def test_token_endpoint_invalid_client(auth_client: AsyncClient):
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": "invalid-client-id",
        "client_secret": "invalid-secret",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_clients(auth_client: AsyncClient):
    # Create client
    resp = await auth_client.post("/api/oauth/clients", data={
        "name": "Test SDK Client",
        "description": "For testing",
        "scopes": "api:read api:write",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "client_id" in data
    assert "client_secret" in data
    assert data["client_secret"].startswith("ics_")
    client_id = data["client_id"]
    client_secret = data["client_secret"]

    # List clients
    resp = await auth_client.get("/api/oauth/clients")
    assert resp.status_code == 200
    clients = resp.json()["clients"]
    assert any(c["client_id"] == client_id for c in clients)

    # Get token
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    assert resp.status_code == 200
    token_data = resp.json()
    assert token_data["token_type"] == "Bearer"
    assert token_data["expires_in"] == 3600

    # Use token to access protected resource
    access_token = token_data["access_token"]
    resp = await auth_client.get("/api/health", headers={
        "Authorization": f"Bearer {access_token}"
    })
    assert resp.status_code == 200

    # Delete client
    resp = await auth_client.delete(f"/api/oauth/clients/{client_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unsupported_grant_type(auth_client: AsyncClient):
    # Create a valid client first so the endpoint reaches grant_type validation
    create_resp = await auth_client.post("/api/oauth/clients", data={
        "name": "Unsupported Grant Test Client",
        "description": "For testing unsupported grant_type",
        "scopes": "api:read",
    })
    assert create_resp.status_code == 200
    client_id = create_resp.json()["client_id"]
    client_secret = create_resp.json()["client_secret"]

    # Try unsupported grant_type with valid client credentials
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    assert resp.status_code == 400
