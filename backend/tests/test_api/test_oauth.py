"""Test OAuth 2.0 endpoints — RFC 6749 + Corti parity patterns.

Phase 1.0 (2026-06-30) added four Corti-style enforcement points:
1. Short-lived 5-minute tokens (replaces 1-hour legacy default)
2. Tenant-Name / X-Tenant header cross-check (cloud mode mandatory)
3. Limited-scope credentials (capability scopes)
4. Realm-routed token URL (path-parameter tenant slug)
"""
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
    # Corti parity (2026-06-30, Phase 1.0): short-lived 5-minute default,
    # not the legacy 1h window. See OAUTH_CLIENT_EXPIRE_SECONDS in config.
    assert token_data["expires_in"] == 300

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


# ────────────────────────────────────────────────────────────────────────────
# Phase 1.0 — Corti parity enforcement (2026-06-30)
# ────────────────────────────────────────────────────────────────────────────


async def _create_client(auth_client: AsyncClient, name: str, scopes: str) -> tuple[str, str]:
    """Helper: mint a fresh OAuth client + return (client_id, client_secret)."""
    resp = await auth_client.post(
        "/api/oauth/clients",
        data={"name": name, "description": "p1.0", "scopes": scopes},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["client_id"], data["client_secret"]


async def _token(auth_client: AsyncClient, *, client_id: str, client_secret: str, scope: str = "api:read api:write") -> dict:
    """Helper: mint a client_credentials token."""
    resp = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_p1_0_short_lived_token_default(auth_client: AsyncClient):
    """Phase 1.0: client_credentials tokens default to 5-minute lifetime."""
    cid, secret = await _create_client(auth_client, "TTL default", "api:read api:write")
    token_data = await _token(auth_client, client_id=cid, client_secret=secret)
    assert token_data["expires_in"] == 300, (
        f"Expected 5-minute default (300s), got {token_data['expires_in']}"
    )


@pytest.mark.asyncio
async def test_p1_0_realm_routed_token_url(auth_client: AsyncClient):
    """Phase 1.0 / Pattern 4: POST /api/oauth/realms/{realm}/token works."""
    cid, secret = await _create_client(auth_client, "Realm-routed", "api:read api:write")
    resp = await auth_client.post(
        "/api/oauth/realms/base/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "api:read api:write",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 300
    assert body["realm"] == "base"
    # Realm is also encoded as the org_id claim so downstream tenant
    # cross-checks succeed without an extra DB hop.
    from jose import jwt
    claims = jwt.get_unverified_claims(body["access_token"])
    assert claims["realm"] == "base"
    assert claims["org_id"] == "base"


@pytest.mark.asyncio
async def test_p1_0_realm_discovery_doc(auth_client: AsyncClient):
    """Phase 1.0: realm discovery doc returns endpoint shape per Corti."""
    resp = await auth_client.get("/api/oauth/realms/base/.well-known/openid-configuration")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_endpoint"] == "/api/oauth/realms/base/token"
    assert "client_credentials" in body["grant_types_supported"]
    assert {"transcribe", "streams", "textgen", "facts"}.issubset(set(body["scopes_supported"]))


@pytest.mark.asyncio
async def test_p1_0_reject_unauthorised_realm_token(auth_client: AsyncClient):
    """Phase 1.0: realm endpoint still rejects unknown client_id."""
    resp = await auth_client.post(
        "/api/oauth/realms/hospital-x/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "icoder-doesnotexist",
            "client_secret": "ics_bogus",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_client"


@pytest.mark.asyncio
async def test_p1_0_capability_scope_intersect(auth_client: AsyncClient):
    """Phase 1.0 / Pattern 3: capability-scoped client mints limited token."""
    cid, secret = await _create_client(auth_client, "STT dictation", "transcribe")
    token_data = await _token(auth_client, client_id=cid, client_secret=secret, scope="transcribe")
    assert token_data["scope"] == "transcribe"
    # Client granted only "transcribe" — asking for "api:read" should fail.
    bad = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
            "scope": "api:read",
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["error"] == "invalid_scope"


@pytest.mark.asyncio
async def test_p1_0_capability_partial_intersect(auth_client: AsyncClient):
    """Phase 1.0: token scope is the intersection of requested and granted."""
    cid, secret = await _create_client(auth_client, "Multi-capability", "transcribe textgen")
    # Request only `transcribe` from a multi-capability client.
    token_data = await _token(auth_client, client_id=cid, client_secret=secret, scope="transcribe")
    assert token_data["scope"] == "transcribe"
    # Request union of granted scopes — issued scope is the granted set.
    token_data = await _token(
        auth_client, client_id=cid, client_secret=secret, scope="transcribe textgen streams",
    )
    issued = set(token_data["scope"].split())
    # Intersection rule: client granted two, request added an ungranted
    # `streams`, the issued scope must NOT include `streams`.
    assert "streams" not in issued
    assert {"transcribe", "textgen"}.issubset(issued)


@pytest.mark.asyncio
async def test_p1_0_tenant_header_passthrough_local_mode(auth_client: AsyncClient):
    """Phase 1.0 / Pattern 2 (local mode): tenant header is OPTIONAL.

    Local dev keeps single-tenant convenience — no header is required.
    The header is recorded on ``request.state.tenant_name`` for handlers
    that want to use it (e.g. log scoping).
    """
    cid, secret = await _create_client(auth_client, "Tenant header passthrough", "api:read")
    # No tenant header → still 200 (local mode).
    resp = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        },
    )
    assert resp.status_code == 200
    # With header but no JWT — also 200; header is recorded but not enforced.
    resp = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        },
        headers={"Tenant-Name": "hospital-xyz"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_p1_0_tenant_header_x_alias(auth_client: AsyncClient):
    """Phase 1.0: ``X-Tenant`` is accepted as a vendor-friendly alias."""
    cid, secret = await _create_client(auth_client, "X-Tenant alias", "api:read")
    resp = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        },
        headers={"X-Tenant": "hospital-abc"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_p1_0_tenant_header_mismatch_with_jwt(auth_client: AsyncClient):
    """Phase 1.0: header != JWT org_id → 400 tenant_header_mismatch.

    The middleware reads the tenant header AND peeks the unverified JWT
    ``org_id`` claim. They must agree. Test targets a non-exempt route
    (``/api/encounters``) so the middleware fires before route-level auth.
    """
    from jose import jwt
    from app.config import settings

    # Forge a JWT whose org_id does NOT match the header we will send.
    forged = jwt.encode(
        {
            "sub": "client-test",
            "type": "client_credentials",
            "scopes": "api:read",
            "owner_id": "tester",
            "org_id": "hospital-zzz",
            "exp": 9_999_999_999,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    resp = await auth_client.get(
        "/api/encounters",
        headers={
            "Authorization": f"Bearer {forged}",
            "Tenant-Name": "hospital-yyy",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "tenant_header_mismatch"


@pytest.mark.asyncio
async def test_p1_0_oauth_client_ttl_cap_to_config(auth_client: AsyncClient):
    """Phase 1.0: per-client ``token_expires_seconds`` is capped to config.

    A caller requesting a 24h lifetime still receives at most the global
    ceiling (5 min in tests). Anything larger is silently downgraded —
    this prevents stale forms from leaking long-lived M2M tokens.
    """
    resp = await auth_client.post(
        "/api/oauth/clients",
        data={
            "name": "TTL cap",
            "scopes": "api:read",
            "token_expires_seconds": "86400",  # 24h attempt
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["token_expires_seconds"] == 300
