"""OAuth list_clients — disabled clients visible by default.

Pre-B-005 follow-up: ``GET /api/oauth/clients`` filtered
``is_active == True`` unconditionally. Disabled clients disappeared from
Console, so the frontend's disabled badge + re-enable action
(``APIClientsPage.tsx:180-181``) never fired. The only re-enable path was
a direct DB UPDATE.

Fix: ``include_disabled`` query param defaults to ``True`` so disabled
clients surface in Console. Pass ``?include_disabled=false`` for
partner-facing listings that should hide them.

Tests (3):
  §1 Default — disabled clients are included.
  §2 Opt-out — ``?include_disabled=false`` hides disabled clients.
  §3 Response carries the ``is_active`` field so frontend can branch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


async def _create_client(ac: AsyncClient, name: str) -> str:
    resp = await ac.post(
        "/api/oauth/clients",
        data={"name": name, "description": name, "scopes": "api:read"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["client_id"]


async def _disable_client(ac: AsyncClient, client_id: str) -> None:
    """Use the DELETE endpoint to soft-disable (it sets is_active=False)."""
    resp = await ac.delete(f"/api/oauth/clients/{client_id}")
    assert resp.status_code == 200, resp.text


# ─────────────────────────────────────────────────────────────────────
# §1 Default — disabled clients included
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_clients_default_includes_disabled(auth_client: AsyncClient):
    """Default GET /api/oauth/clients returns both active + disabled clients."""
    active_cid = await _create_client(auth_client, "B-005 Active Client")
    disabled_cid = await _create_client(auth_client, "B-005 Disabled Client")
    await _disable_client(auth_client, disabled_cid)

    resp = await auth_client.get("/api/oauth/clients")
    assert resp.status_code == 200
    clients = resp.json()["clients"]
    cids = {c["client_id"] for c in clients}
    assert active_cid in cids, "active client must be visible"
    assert disabled_cid in cids, (
        "B-005 fix: disabled client must be visible by default so Console "
        "can render the disabled badge + re-enable action"
    )


# ─────────────────────────────────────────────────────────────────────
# §2 Opt-out — ?include_disabled=false hides disabled
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_clients_include_disabled_false_hides_disabled(
    auth_client: AsyncClient,
):
    """?include_disabled=false restores the pre-B-005 behaviour (active only)."""
    active_cid = await _create_client(auth_client, "B-005 Optout Active")
    disabled_cid = await _create_client(auth_client, "B-005 Optout Disabled")
    await _disable_client(auth_client, disabled_cid)

    resp = await auth_client.get("/api/oauth/clients?include_disabled=false")
    assert resp.status_code == 200
    clients = resp.json()["clients"]
    cids = {c["client_id"] for c in clients}
    assert active_cid in cids
    assert disabled_cid not in cids, (
        "?include_disabled=false must hide disabled clients for partner-facing listings"
    )


# ─────────────────────────────────────────────────────────────────────
# §3 is_active field present in response
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_clients_response_carries_is_active_field(
    auth_client: AsyncClient,
):
    """Each client dict carries is_active so frontend can branch on it."""
    cid = await _create_client(auth_client, "B-005 IsActive Probe")
    await _disable_client(auth_client, cid)

    resp = await auth_client.get("/api/oauth/clients")
    assert resp.status_code == 200
    by_id = {c["client_id"]: c for c in resp.json()["clients"]}
    assert "is_active" in by_id[cid], (
        "B-005 follow-up: response must include is_active so frontend "
        "APIClientsPage.tsx:180 c.is_active === false branch can fire"
    )
    assert by_id[cid]["is_active"] is False
