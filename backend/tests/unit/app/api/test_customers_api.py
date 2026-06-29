"""Customers API tests — Corti parity for Embedded Assistant end-user mgmt.

Covers:
* list with pagination + search + region filter
* create with valid suffix → 201 + returns public customer_id
* create with invalid suffix → 400 INVALID_CUSTOMER_ID_SUFFIX
* create with duplicate customer_id → 409 CUSTOMER_ID_TAKEN
* get existing → 200
* get non-existing → 404 CUSTOMER_NOT_FOUND
* delete existing → 204
"""
from __future__ import annotations

import sys
import os
from urllib.parse import quote

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _enc(customer_id: str) -> str:
    return quote(customer_id, safe="")


pytestmark = pytest.mark.asyncio


class TestCreateCustomer:
    async def test_create_returns_201_with_customer_id(self, auth_client):
        r = await auth_client.post(
            "/api/customers",
            json={
                "display_name": "Beijing Clinic A",
                "customer_id_suffix": "clinic-a",
                "region": "cn",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["display_name"] == "Beijing Clinic A"
        assert body["region"] == "cn"
        assert body["nfr"] == 0
        # public customer_id has the org slug prefix
        assert "/" in body["customer_id"]
        assert body["customer_id"].endswith("/clinic-a")
        assert body.get("created_at")

    async def test_create_invalid_suffix_returns_400(self, auth_client):
        # spaces are not allowed by the regex
        r = await auth_client.post(
            "/api/customers",
            json={
                "display_name": "Bad",
                "customer_id_suffix": "has spaces",
                "region": "us",
            },
        )
        assert r.status_code == 400, r.text
        body = r.json()
        detail = body.get("detail") or {}
        assert detail.get("error_code") == "INVALID_CUSTOMER_ID_SUFFIX"

    async def test_create_duplicate_returns_409(self, auth_client):
        payload = {
            "display_name": "Dup",
            "customer_id_suffix": "dup-test",
            "region": "eu",
        }
        r1 = await auth_client.post("/api/customers", json=payload)
        assert r1.status_code == 201, r1.text
        r2 = await auth_client.post("/api/customers", json=payload)
        assert r2.status_code == 409, r2.text
        body = r2.json()
        detail = body.get("detail") or {}
        assert detail.get("error_code") == "CUSTOMER_ID_TAKEN"


class TestListCustomers:
    async def test_list_returns_pagination_shape(self, auth_client):
        r = await auth_client.get("/api/customers")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "customers" in body
        assert "total" in body
        assert body["page"] == 1
        assert body["page_size"] == 20

    async def test_list_search_filters_by_display_name(self, auth_client):
        await auth_client.post(
            "/api/customers",
            json={
                "display_name": "Searchable Hospital",
                "customer_id_suffix": "searchable",
                "region": "cn",
            },
        )
        r = await auth_client.get("/api/customers", params={"search": "Searchable"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        assert any(c["display_name"] == "Searchable Hospital" for c in body["customers"])

    async def test_list_region_filter(self, auth_client):
        await auth_client.post(
            "/api/customers",
            json={
                "display_name": "EU Test",
                "customer_id_suffix": "eu-test",
                "region": "eu",
            },
        )
        r = await auth_client.get("/api/customers", params={"region": "eu"})
        assert r.status_code == 200, r.text
        body = r.json()
        # every returned customer must be EU
        for c in body["customers"]:
            assert c["region"] == "eu"


class TestGetCustomer:
    async def test_get_returns_200(self, auth_client):
        create = await auth_client.post(
            "/api/customers",
            json={
                "display_name": "Get Test",
                "customer_id_suffix": "get-test",
                "region": "us",
            },
        )
        assert create.status_code == 201, create.text
        cid = create.json()["customer_id"]
        r = await auth_client.get(f"/api/customers/{_enc(cid)}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["customer_id"] == cid
        assert body["display_name"] == "Get Test"

    async def test_get_unknown_returns_404(self, auth_client):
        r = await auth_client.get("/api/customers/does-not-exist")
        assert r.status_code == 404, r.text
        body = r.json()
        detail = body.get("detail") or {}
        assert detail.get("error_code") == "CUSTOMER_NOT_FOUND"


class TestDeleteCustomer:
    async def test_delete_returns_204_then_404_on_get(self, auth_client):
        create = await auth_client.post(
            "/api/customers",
            json={
                "display_name": "Delete Me",
                "customer_id_suffix": "delete-me",
                "region": "cn",
            },
        )
        assert create.status_code == 201, create.text
        cid = create.json()["customer_id"]
        r = await auth_client.delete(f"/api/customers/{_enc(cid)}")
        assert r.status_code == 204, r.text
        # subsequent GET must 404
        r2 = await auth_client.get(f"/api/customers/{_enc(cid)}")
        assert r2.status_code == 404, r2.text

    async def test_delete_unknown_returns_404(self, auth_client):
        r = await auth_client.delete("/api/customers/never-existed")
        assert r.status_code == 404, r.text