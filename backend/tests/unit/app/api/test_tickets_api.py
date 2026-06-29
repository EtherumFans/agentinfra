"""Tickets API tests — Corti parity for /tickets (Tickets Portal).

Covers:
* create → 201
* list with pagination + search + status + priority + created_by_me
* get existing → 200, unknown → 404 TICKET_NOT_FOUND
* patch (status / priority / subject / description) → 200
* delete → 204, unknown → 404
"""
from __future__ import annotations

import sys
import os

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


pytestmark = pytest.mark.asyncio


class TestCreateTicket:
    async def test_create_returns_201_with_defaults(self, auth_client):
        r = await auth_client.post(
            "/api/tickets",
            json={"subject": "Need help with API"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["subject"] == "Need help with API"
        assert body["status"] == "open"
        assert body["priority"] == "medium"
        assert body["id"]

    async def test_create_with_priority_high(self, auth_client):
        r = await auth_client.post(
            "/api/tickets",
            json={
                "subject": "Critical bug",
                "description": "Server returns 500 on POST /api/anything",
                "priority": "high",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["priority"] == "high"
        assert body["description"] == "Server returns 500 on POST /api/anything"

    async def test_create_empty_subject_400(self, auth_client):
        r = await auth_client.post("/api/tickets", json={"subject": ""})
        assert r.status_code == 422, r.text  # pydantic min_length=1


class TestListTickets:
    async def test_list_returns_pagination_shape(self, auth_client):
        await auth_client.post("/api/tickets", json={"subject": "Test 1"})
        await auth_client.post("/api/tickets", json={"subject": "Test 2"})
        r = await auth_client.get("/api/tickets")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 2
        assert body["page"] == 1
        assert body["page_size"] == 20

    async def test_list_search_filters(self, auth_client):
        await auth_client.post("/api/tickets", json={"subject": "Unique search term"})
        r = await auth_client.get("/api/tickets", params={"search": "Unique search"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        assert any("Unique search" in t["subject"] for t in body["tickets"])

    async def test_list_status_filter(self, auth_client):
        await auth_client.post("/api/tickets", json={"subject": "Status test"})
        r = await auth_client.get("/api/tickets", params={"status": "open"})
        assert r.status_code == 200, r.text
        for t in r.json()["tickets"]:
            assert t["status"] == "open"


class TestGetTicket:
    async def test_get_returns_200(self, auth_client):
        create = await auth_client.post("/api/tickets", json={"subject": "Get me"})
        assert create.status_code == 201, create.text
        tid = create.json()["id"]
        r = await auth_client.get(f"/api/tickets/{tid}")
        assert r.status_code == 200, r.text
        assert r.json()["subject"] == "Get me"

    async def test_get_unknown_returns_404(self, auth_client):
        r = await auth_client.get("/api/tickets/never-existed")
        assert r.status_code == 404, r.text
        body = r.json()
        assert body["detail"]["error_code"] == "TICKET_NOT_FOUND"


class TestUpdateTicket:
    async def test_patch_status(self, auth_client):
        create = await auth_client.post("/api/tickets", json={"subject": "Status patch"})
        tid = create.json()["id"]
        r = await auth_client.patch(f"/api/tickets/{tid}", json={"status": "in_progress"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "in_progress"

    async def test_patch_priority(self, auth_client):
        create = await auth_client.post("/api/tickets", json={"subject": "Priority patch"})
        tid = create.json()["id"]
        r = await auth_client.patch(f"/api/tickets/{tid}", json={"priority": "high"})
        assert r.status_code == 200, r.text
        assert r.json()["priority"] == "high"

    async def test_patch_unknown_returns_404(self, auth_client):
        r = await auth_client.patch("/api/tickets/nope", json={"status": "closed"})
        assert r.status_code == 404, r.text


class TestDeleteTicket:
    async def test_delete_returns_204_then_404(self, auth_client):
        create = await auth_client.post("/api/tickets", json={"subject": "Delete"})
        tid = create.json()["id"]
        d = await auth_client.delete(f"/api/tickets/{tid}")
        assert d.status_code == 204, d.text
        g = await auth_client.get(f"/api/tickets/{tid}")
        assert g.status_code == 404, g.text

    async def test_delete_unknown_returns_404(self, auth_client):
        r = await auth_client.delete("/api/tickets/never-existed")
        assert r.status_code == 404, r.text