from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select


async def _register(client, label: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post("/api/auth/register", json={
        "username": f"{label}-{suffix}",
        "email": f"{label}-{suffix}@example.com",
        "password": "password123",
        "full_name": f"{label} Test",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_development_ledger_is_explicit_and_fails_closed_on_overdraft(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    monkeypatch.setenv("ICODER_BILLING_SIMULATION", "true")
    monkeypatch.setenv("ICODER_BILLING_LOW_BALANCE_THRESHOLD", "8")
    owner = await _register(client, "billing-sim")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}

    initial = await client.get("/api/billing/balance", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["balance"] == 0.0
    assert initial.json()["simulation"] is True
    assert initial.json()["alerts"] == {"low_balance": True, "threshold": 8.0}

    credited = await client.post(
        "/api/billing/credits",
        headers=headers,
        params={"amount": 10},
    )
    assert credited.status_code == 200, credited.text
    assert credited.json() == {
        "status": "success",
        "added": 10.0,
        "new_balance": 10.0,
        "simulation": True,
    }

    debited = await client.post(
        "/api/billing/simulation/debit",
        headers=headers,
        json={"amount": 3, "reference": "synthetic-run-1"},
    )
    assert debited.status_code == 200, debited.text
    assert debited.json()["new_balance"] == 7.0
    assert debited.json()["alerts"] == {"low_balance": True, "threshold": 8.0}

    overdraft = await client.post(
        "/api/billing/simulation/debit",
        headers=headers,
        json={"amount": 8, "reference": "synthetic-run-overdraft"},
    )
    assert overdraft.status_code == 409
    assert overdraft.json()["detail"]["code"] == "INSUFFICIENT_CREDITS"
    assert overdraft.json()["detail"]["balance"] == 7.0

    transactions = await client.get(
        "/api/billing/transactions",
        headers=headers,
    )
    assert transactions.status_code == 200
    assert transactions.json()["total"] == 2
    assert transactions.json()["page"] == 1
    assert transactions.json()["page_size"] == 20
    assert {row["type"] for row in transactions.json()["transactions"]} == {"credit", "debit"}

    first_page = await client.get(
        "/api/billing/transactions",
        headers=headers,
        params={"page": 1, "page_size": 1},
    )
    second_page = await client.get(
        "/api/billing/transactions",
        headers=headers,
        params={"page": 2, "page_size": 1},
    )
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == second_page.json()["total"] == 2
    assert first_page.json()["page"] == 1
    assert second_page.json()["page"] == 2
    assert len(first_page.json()["transactions"]) == 1
    assert len(second_page.json()["transactions"]) == 1
    assert first_page.json()["transactions"][0]["id"] != second_page.json()["transactions"][0]["id"]

    legacy_limit = await client.get(
        "/api/billing/transactions",
        headers=headers,
        params={"limit": 1, "page": 99, "page_size": 99},
    )
    assert legacy_limit.status_code == 200
    assert legacy_limit.json()["total"] == 2
    assert legacy_limit.json()["page"] == 1
    assert legacy_limit.json()["page_size"] == 1
    assert len(legacy_limit.json()["transactions"]) == 1

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                    select(AuditLog).where(
                        AuditLog.action.in_([
                        "billing.credit.simulation",
                        "billing.debit.simulation",
                    ]),
                )
            )
        ).scalars().all()
    assert {row.action for row in rows} == {
        "billing.credit.simulation",
        "billing.debit.simulation",
    }
    assert all(row.organization_id for row in rows)
    assert all("api_key" not in str(row.details).lower() for row in rows)


@pytest.mark.asyncio
async def test_billing_mutations_are_disabled_outside_local_development(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from app.config import settings

    owner = await _register(client, "billing-cloud")
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    previous_env = settings.APP_ENV
    settings.APP_ENV = "cloud"
    try:
        response = await client.post(
            "/api/billing/credits",
            headers=headers,
            params={"amount": 1},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "BILLING_SIMULATION_DISABLED"
    finally:
        settings.APP_ENV = previous_env
