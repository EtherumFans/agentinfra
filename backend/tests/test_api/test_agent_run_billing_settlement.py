"""Development Agent Run preauthorization + idempotent settlement E2E."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException


async def _register(client) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post("/api/auth/register", json={
        "username": f"run-billing-{suffix}",
        "email": f"run-billing-{suffix}@example.com",
        "password": "password123",
        "full_name": "Run Billing Test",
        "organization_name": f"Run Billing Test Org {suffix}",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    ("agent_id", "scope", "allowed"),
    [
        ("medical-coding-agent", "medical-coding:run", True),
        ("clinical-documentation-improvement-agent", "cdi:run", True),
        ("drg-analyzer", "drg-dip:run", True),
        ("diagnosis-extractor", "agents:run", True),
        ("diagnosis-extractor", "api:write", True),
        ("diagnosis-extractor", "runs:read", False),
        ("drg-analyzer", "medical-coding:run", False),
    ],
)
def test_agent_run_oauth_scope_matrix(
    agent_id: str,
    scope: str,
    allowed: bool,
) -> None:
    from app.api.agent_run import _require_agent_run_scope

    principal = {"scopes": [scope]}
    if allowed:
        _require_agent_run_scope(agent_id, principal)
        return
    with pytest.raises(HTTPException) as exc:
        _require_agent_run_scope(agent_id, principal)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "INSUFFICIENT_SCOPE"


def test_billing_principal_lock_compiles_to_postgresql_for_update() -> None:
    from sqlalchemy.dialects import postgresql

    from app.services.run_billing_settlement import billing_principal_lock_statement

    sql = str(
        billing_principal_lock_statement("user-owner")
        .compile(dialect=postgresql.dialect())
    ).upper()
    assert "FOR UPDATE" in sql
    assert "USERS.ID" in sql


@pytest.mark.asyncio
async def test_agent_run_preauthorizes_and_settles_exactly_once(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from app.api import agent_run
    from app.main import app
    from app.middleware.auth import get_current_user_or_oauth_client

    monkeypatch.setenv("ICODER_BILLING_SIMULATION", "true")
    monkeypatch.setenv("ICODER_AGENT_RUN_BILLING_ENFORCED", "true")
    monkeypatch.setenv("ICODER_AGENT_RUN_RESERVE_CNY", "0.05")

    # ``needs_auth`` removes the user/org overrides. The hybrid Agent Run
    # dependency is separate, so remove its test bypass for this real-JWT E2E.
    saved_hybrid = app.dependency_overrides.pop(
        get_current_user_or_oauth_client, None,
    )
    calls = 0
    cost_amount = 0.013

    async def fake_run_via_provider_registry(**kwargs):
        nonlocal calls, cost_amount
        calls += 1
        return agent_run.AgentRunResponse(
            agent_id=kwargs["agent_id"],
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            runtime_mode="rule_engine",
            latency_ms=7,
            cost={"amount": cost_amount, "currency": "CNY"},
            summary="Synthetic deterministic result",
            result={"review_conclusion": "PASS"},
            manual_review_required=True,
        )

    monkeypatch.setattr(
        agent_run, "_run_via_provider_registry", fake_run_via_provider_registry,
    )
    try:
        owner = await _register(client)
        headers = {"Authorization": f"Bearer {owner['access_token']}"}
        body = {
            "input": {
                "text": "合成病例：验证本地预算闭环。",
                "extra": {"codes": ["Z00.0"]},
            },
            "include_trace": True,
        }

        denied = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers={**headers, "Idempotency-Key": f"denied-{uuid.uuid4().hex}"},
            json=body,
        )
        assert denied.status_code == 402, denied.text
        assert denied.json()["detail"]["code"] == "INSUFFICIENT_CREDITS"
        assert calls == 0, "preauthorization denial must happen before provider execution"

        credited = await client.post(
            "/api/billing/credits", headers=headers, params={"amount": 1},
        )
        assert credited.status_code == 200, credited.text

        key = f"settled-{uuid.uuid4().hex}"
        first = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers={**headers, "Idempotency-Key": key},
            json=body,
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["error"] is False
        assert first_body["billing"] == {
            "simulation": True,
            "status": "SETTLED",
            "reserved_amount": 0.05,
            "settled_amount": 0.013,
            "balance_after": 0.987,
            "currency": "CNY",
            "error_code": None,
        }

        replay = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers={**headers, "Idempotency-Key": key},
            json=body,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["run_id"] == first_body["run_id"]
        assert replay.json()["billing"] == first_body["billing"]
        assert calls == 1, "idempotent replay must not execute or settle twice"

        balance = await client.get("/api/billing/balance", headers=headers)
        assert balance.status_code == 200, balance.text
        assert balance.json()["balance"] == pytest.approx(0.987)
        assert balance.json()["reserved"] == 0.0
        assert balance.json()["available"] == pytest.approx(0.987)

        settlements = await client.get(
            "/api/billing/run-settlements", headers=headers,
        )
        assert settlements.status_code == 200, settlements.text
        matching = [
            item for item in settlements.json()["items"]
            if item["run_id"] == first_body["run_id"]
        ]
        assert len(matching) == 1
        assert matching[0]["status"] == "SETTLED"

        transactions = await client.get(
            "/api/billing/transactions", headers=headers,
        )
        api_usage = [
            row for row in transactions.json()["transactions"]
            if row.get("source") == "api_usage"
        ]
        assert len(api_usage) == 1

        # Exercise the honest overage path: provider-reported actual cost can
        # exceed the conservative reservation. The clinical payload is
        # withheld, the reservation remains visible, and a top-up + retry
        # settles the same run exactly once without re-running the Agent.
        cost_amount = 2.0
        overage = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers={
                **headers,
                "Idempotency-Key": f"overage-{uuid.uuid4().hex}",
            },
            json=body,
        )
        assert overage.status_code == 200, overage.text
        overage_body = overage.json()
        assert overage_body["error"] is True
        assert overage_body["error_reason"] == "billing_settlement_failed"
        assert overage_body["cost"] == {"amount": 2.0, "currency": "CNY"}
        assert overage_body["billing"]["status"] == "SETTLEMENT_FAILED"

        held = await client.get("/api/billing/balance", headers=headers)
        assert held.json()["reserved"] == 0.05
        assert held.json()["available"] == pytest.approx(0.937)

        topped_up = await client.post(
            "/api/billing/credits", headers=headers, params={"amount": 2},
        )
        assert topped_up.status_code == 200, topped_up.text
        retried = await client.post(
            f"/api/billing/run-settlements/{overage_body['run_id']}/retry",
            headers=headers,
        )
        assert retried.status_code == 200, retried.text
        assert retried.json()["status"] == "SETTLED"
        assert retried.json()["settled_amount"] == 2.0

        retried_again = await client.post(
            f"/api/billing/run-settlements/{overage_body['run_id']}/retry",
            headers=headers,
        )
        assert retried_again.status_code == 200, retried_again.text
        assert retried_again.json() == retried.json()
        assert calls == 2

        final_balance = await client.get("/api/billing/balance", headers=headers)
        assert final_balance.json()["balance"] == pytest.approx(0.987)
        assert final_balance.json()["reserved"] == 0.0
    finally:
        if saved_hybrid is not None:
            app.dependency_overrides[get_current_user_or_oauth_client] = saved_hybrid


@pytest.mark.asyncio
async def test_oauth_agent_run_scope_and_owner_ledger_settlement(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from app.api import agent_run
    from app.main import app
    from app.middleware.auth import get_current_user_or_oauth_client

    monkeypatch.setenv("ICODER_BILLING_SIMULATION", "true")
    monkeypatch.setenv("ICODER_AGENT_RUN_BILLING_ENFORCED", "true")
    monkeypatch.setenv("ICODER_AGENT_RUN_RESERVE_CNY", "0.05")
    saved_hybrid = app.dependency_overrides.pop(
        get_current_user_or_oauth_client, None,
    )
    calls = 0

    async def fake_run_via_provider_registry(**kwargs):
        nonlocal calls
        calls += 1
        return agent_run.AgentRunResponse(
            agent_id=kwargs["agent_id"],
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            runtime_mode="rule_engine",
            latency_ms=4,
            cost={"amount": 0.02, "currency": "CNY"},
            summary="Synthetic OAuth result",
            result={"review_conclusion": "PASS"},
            manual_review_required=True,
        )

    monkeypatch.setattr(
        agent_run, "_run_via_provider_registry", fake_run_via_provider_registry,
    )
    try:
        owner = await _register(client)
        owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
        credited = await client.post(
            "/api/billing/credits",
            headers=owner_headers,
            params={"amount": 1},
        )
        assert credited.status_code == 200, credited.text

        async def create_token(
            scopes: str,
            *,
            allowed_agent_ids: list[str] | None = None,
            allowed_purposes: list[str] | None = None,
        ) -> str:
            created = await client.post(
                "/api/clients",
                headers=owner_headers,
                json={
                    "name": f"Billing {scopes}",
                    "scopes": scopes,
                    "allowed_agent_ids": allowed_agent_ids or [],
                    "allowed_purposes": allowed_purposes or [],
                },
            )
            assert created.status_code == 201, created.text
            credentials = created.json()
            token = await client.post(
                "/api/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "scope": scopes,
                },
            )
            assert token.status_code == 200, token.text
            return token.json()["access_token"]

        read_token = await create_token("runs:read")
        denied = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers={"Authorization": f"Bearer {read_token}"},
            json={"input": {"text": "合成只读 scope 拒绝用例。"}},
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["detail"]["code"] == "INSUFFICIENT_SCOPE"
        assert calls == 0

        run_token = await create_token(
            "agents:run",
            allowed_agent_ids=["compliance-guardrail-agent"],
            allowed_purposes=["treatment"],
        )
        oauth_headers = {
            "Authorization": f"Bearer {run_token}",
            "Idempotency-Key": f"oauth-billing-{uuid.uuid4().hex}",
        }
        body = {
            "purpose_of_use": "treatment",
            "input": {
                "text": "合成 API Client 账本用例。",
                "extra": {"codes": ["Z00.0"]},
            }
        }
        first = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers=oauth_headers,
            json=body,
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["error"] is False
        assert first_body["billing"]["status"] == "SETTLED"
        assert first_body["billing"]["settled_amount"] == 0.02

        replay = await client.post(
            "/api/v1/agents/compliance-guardrail-agent/run",
            headers=oauth_headers,
            json=body,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["run_id"] == first_body["run_id"]
        assert calls == 1

        balance = await client.get("/api/billing/balance", headers=owner_headers)
        assert balance.status_code == 200, balance.text
        assert balance.json()["balance"] == pytest.approx(0.98)
        assert balance.json()["reserved"] == 0.0

        settlements = await client.get(
            "/api/billing/run-settlements", headers=owner_headers,
        )
        matching = [
            item for item in settlements.json()["items"]
            if item["run_id"] == first_body["run_id"]
        ]
        assert len(matching) == 1
        assert matching[0]["status"] == "SETTLED"
    finally:
        if saved_hybrid is not None:
            app.dependency_overrides[get_current_user_or_oauth_client] = saved_hybrid


@pytest.mark.asyncio
async def test_reconcile_releases_only_stale_non_active_reservations(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.billing_run_settlement import BillingRunSettlement
    from app.models.run_history import RunHistoryModel
    from app.services.run_lifecycle import RunStatus

    monkeypatch.setenv("ICODER_BILLING_SIMULATION", "true")
    monkeypatch.setenv("ICODER_AGENT_RUN_BILLING_ENFORCED", "true")
    owner = await _register(client)
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    user_id = owner["user"]["id"]
    org_id = owner["current_org_id"]
    orphan_run_id = f"run-orphan-{uuid.uuid4().hex}"
    active_run_id = f"run-active-{uuid.uuid4().hex}"
    stale_settling_run_id = f"run-settling-{uuid.uuid4().hex}"
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)

    async with AsyncSessionLocal() as db:
        db.add_all([
            BillingRunSettlement(
                organization_id=org_id,
                user_id=user_id,
                run_id=orphan_run_id,
                status="RESERVED",
                reserved_amount=0.05,
                settled_amount=0.0,
                updated_at=old,
            ),
            BillingRunSettlement(
                organization_id=org_id,
                user_id=user_id,
                run_id=active_run_id,
                status="SETTLING",
                reserved_amount=0.05,
                settled_amount=0.02,
                updated_at=old,
            ),
            BillingRunSettlement(
                organization_id=org_id,
                user_id=user_id,
                run_id=stale_settling_run_id,
                status="SETTLING",
                reserved_amount=0.05,
                settled_amount=0.03,
                updated_at=old,
            ),
            RunHistoryModel(
                organization_id=org_id,
                user_id=user_id,
                agent_id="compliance-guardrail-agent",
                run_id=active_run_id,
                status=RunStatus.RUNNING,
                input_text="",
                output_summary="",
            ),
        ])
        await db.commit()

    reconciled = await client.post(
        "/api/billing/run-settlements/reconcile-stale",
        headers=headers,
        params={"older_than_seconds": 300},
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json() == {
        "simulation": True,
        "released": 1,
        "marked_retryable": 1,
        "skipped_active": 1,
        "inspected": 3,
        "older_than_seconds": 300,
    }

    settlements = await client.get(
        "/api/billing/run-settlements", headers=headers,
    )
    by_run = {item["run_id"]: item for item in settlements.json()["items"]}
    assert by_run[orphan_run_id]["status"] == "RELEASED"
    assert by_run[orphan_run_id]["error_code"] == "STALE_RESERVATION_RELEASED"
    assert by_run[active_run_id]["status"] == "SETTLING"
    assert by_run[stale_settling_run_id]["status"] == "SETTLEMENT_FAILED"
    assert by_run[stale_settling_run_id]["error_code"] == "STALE_SETTLING_REQUIRES_RETRY"

    balance = await client.get("/api/billing/balance", headers=headers)
    assert balance.status_code == 200, balance.text
    assert balance.json()["reserved"] == 0.1
