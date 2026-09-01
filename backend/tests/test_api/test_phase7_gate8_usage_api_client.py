"""Phase 7 Gate 8 — Usage × API Client attribution closed loop.

Covers:

  §13.1 /summary api_client_id filter
    - Unfiltered: aggregates across all clients
    - api_client_id="partner-a": only partner-a's runs
    - api_client_id="console" sentinel: only Console runs (NULL api_client_id)
    - Combined with agent_id filter

  §13.2 /by-agent api_client_id filter
    - Per-agent breakdown scoped to one partner
    - "console" sentinel scopes to Console-only

  §13.3 /by-client endpoint (NEW)
    - Returns one row per api_client_id (partner-attributed)
    - Plus a synthetic "console" row for unattributed runs
    - Sorted by cost desc; empty bucket omitted
"""
from __future__ import annotations

import os
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_db(client: TestClient):
    """Seed run_history with mixed Console + partner runs.

    Layout (user_id="u-test-bypass" = the user that
    ICODER_DISABLE_AUTH_FOR_TESTS resolves to via conftest):
      - 2 runs partner-a × medical-coding-agent (cost 0.10 + 0.20)
      - 1 run  partner-a × cdi-agent            (cost 0.05)
      - 1 run  partner-b × medical-coding-agent (cost 0.50)
      - 2 runs Console    × medical-coding-agent (cost 0.01 + 0.02)

    NOTE: clears ALL run_history rows for user_id="u-test-bypass" first
    so other tests' agent_run calls (Gate 4) don't leak cost into our
    deterministic assertions.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    rows = [
        # (run_id, agent_id, api_client_id, cost_usd, latency_ms)
        ("run-g8-1", "medical-coding-agent", "partner-a", 0.10, 3000),
        ("run-g8-2", "medical-coding-agent", "partner-a", 0.20, 4000),
        ("run-g8-3", "cdi-agent",            "partner-a", 0.05, 5000),
        ("run-g8-4", "medical-coding-agent", "partner-b", 0.50, 2500),
        ("run-g8-5", "medical-coding-agent", None,        0.01, 1500),
        ("run-g8-6", "medical-coding-agent", None,        0.02, 1800),
    ]
    now = datetime.now(UTC)

    import asyncio

    async def _seed():
        async with AsyncSessionLocal() as db:
            # Clear ALL rows for the test user so prior tests' real
            # agent_run calls don't pollute our deterministic totals.
            await db.execute(text(
                "DELETE FROM run_history WHERE user_id = 'u-test-bypass'"
            ))
            for run_id, agent_id, api_client_id, cost, lat in rows:
                row = RunHistoryModel(
                    organization_id="org_default1",
                    run_id=run_id,
                    agent_id=agent_id,
                    api_client_id=api_client_id,
                    user_id="u-test-bypass",
                    cost_usd=cost,
                    latency_ms=lat,
                    runtime_mode="corti_like_fast",
                    status="COMPLETED",
                    created_at=now,
                    tenancy_classification="MODERN",
                )
                db.add(row)
            await db.commit()

    asyncio.run(_seed())
    yield
    # teardown
    async def _clear():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id LIKE 'run-g8-%'"
            ))
            await db.commit()
    asyncio.run(_clear())


# ────────────────────────────────────────────────────────────────────
# §13.1 /summary api_client_id filter
# ────────────────────────────────────────────────────────────────────


def test_summary_unfiltered_aggregates_all_clients(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/summary?days=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 0.10 + 0.20 + 0.05 + 0.50 + 0.01 + 0.02 = 0.88
    assert abs(body["credits_used"] - 0.88) < 1e-6
    assert body["filters"]["api_client_id"] is None


def test_summary_filtered_by_partner_a_returns_only_partner_a_runs(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/summary?days=1&api_client_id=partner-a")
    assert resp.status_code == 200
    body = resp.json()
    # 0.10 + 0.20 + 0.05 = 0.35
    assert abs(body["credits_used"] - 0.35) < 1e-6
    assert body["filters"]["api_client_id"] == "partner-a"


def test_summary_filtered_by_partner_b_returns_only_partner_b_runs(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/summary?days=1&api_client_id=partner-b")
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["credits_used"] - 0.50) < 1e-6


def test_summary_console_sentinel_returns_only_console_runs(
    client: TestClient, seeded_db
) -> None:
    """api_client_id=console (case-insensitive) filters to NULL api_client_id."""
    resp = client.get("/api/usage/summary?days=1&api_client_id=console")
    assert resp.status_code == 200
    body = resp.json()
    # 0.01 + 0.02 = 0.03
    assert abs(body["credits_used"] - 0.03) < 1e-6


def test_summary_console_sentinel_case_insensitive(
    client: TestClient, seeded_db
) -> None:
    """CONSOLE / Console / console all map to the same sentinel."""
    for variant in ("CONSOLE", "Console", "console"):
        resp = client.get(f"/api/usage/summary?days=1&api_client_id={variant}")
        assert resp.status_code == 200
        body = resp.json()
        assert abs(body["credits_used"] - 0.03) < 1e-6, variant


def test_summary_combines_api_client_id_with_agent_id(
    client: TestClient, seeded_db
) -> None:
    """partner-a × cdi-agent should return only 0.05."""
    resp = client.get(
        "/api/usage/summary?days=1&api_client_id=partner-a&agent_id=cdi-agent"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["credits_used"] - 0.05) < 1e-6
    assert body["filters"]["agent_id"] == "cdi-agent"
    assert body["filters"]["api_client_id"] == "partner-a"


def test_summary_unknown_api_client_returns_zero(
    client: TestClient, seeded_db
) -> None:
    """Filter that matches no rows returns credits_used=0, not an error."""
    resp = client.get("/api/usage/summary?days=1&api_client_id=ghost-partner")
    assert resp.status_code == 200
    body = resp.json()
    assert body["credits_used"] == 0.0


# ────────────────────────────────────────────────────────────────────
# §13.2 /by-agent api_client_id filter
# ────────────────────────────────────────────────────────────────────


def test_by_agent_unfiltered_lists_all_agents(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/by-agent?days=1")
    assert resp.status_code == 200
    body = resp.json()
    agent_ids = {it["agent_id"] for it in body["items"]}
    assert agent_ids == {"medical-coding-agent", "cdi-agent"}
    # medical-coding (0.83 total) > cdi (0.05)
    items_by_agent = {it["agent_id"]: it for it in body["items"]}
    assert items_by_agent["medical-coding-agent"]["run_count"] == 5
    assert items_by_agent["cdi-agent"]["run_count"] == 1


def test_by_agent_filtered_by_partner_a(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/by-agent?days=1&api_client_id=partner-a")
    assert resp.status_code == 200
    body = resp.json()
    items_by_agent = {it["agent_id"]: it for it in body["items"]}
    # partner-a: 2 medical-coding + 1 cdi
    assert items_by_agent["medical-coding-agent"]["run_count"] == 2
    assert items_by_agent["cdi-agent"]["run_count"] == 1
    # cost: 0.30 / 0.05
    assert abs(items_by_agent["medical-coding-agent"]["cost"] - 0.30) < 1e-6
    assert abs(items_by_agent["cdi-agent"]["cost"] - 0.05) < 1e-6


def test_by_agent_console_sentinel(
    client: TestClient, seeded_db
) -> None:
    """Console runs are all medical-coding."""
    resp = client.get("/api/usage/by-agent?days=1&api_client_id=console")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["agent_id"] == "medical-coding-agent"
    assert body["items"][0]["run_count"] == 2


# ────────────────────────────────────────────────────────────────────
# §13.3 /by-client endpoint
# ────────────────────────────────────────────────────────────────────


def test_by_client_returns_per_partner_plus_console_bucket(
    client: TestClient, seeded_db
) -> None:
    resp = client.get("/api/usage/by-client?days=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_client = {it["api_client_id"]: it for it in body["items"]}
    # 3 buckets: partner-a, partner-b, console
    assert set(by_client.keys()) == {"partner-a", "partner-b", "console"}
    # partner-b is most expensive (0.50), should be first
    assert body["items"][0]["api_client_id"] == "partner-b"
    # cost sums
    assert abs(by_client["partner-a"]["cost"] - 0.35) < 1e-6
    assert abs(by_client["partner-b"]["cost"] - 0.50) < 1e-6
    assert abs(by_client["console"]["cost"] - 0.03) < 1e-6
    # run counts
    assert by_client["partner-a"]["run_count"] == 3
    assert by_client["partner-b"]["run_count"] == 1
    assert by_client["console"]["run_count"] == 2
    # total
    assert abs(body["total_cost"] - 0.88) < 1e-6


def test_by_client_empty_when_no_runs(client: TestClient) -> None:
    """No seeded runs → empty items, zero total."""
    # Use a fresh DB state by deleting any leftover rows from prior tests.
    from app.database import AsyncSessionLocal
    import asyncio

    async def _clear():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE run_id LIKE 'run-g8-%'"
            ))
            await db.commit()
    asyncio.run(_clear())

    resp = client.get("/api/usage/by-client?days=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total_cost"] == 0.0


def test_by_client_omits_console_bucket_when_no_console_runs(
    client: TestClient, seeded_db
) -> None:
    """If all runs are partner-attributed, the console bucket is omitted."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    import asyncio

    async def _drop_console():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history "
                "WHERE run_id IN ('run-g8-5', 'run-g8-6')"
            ))
            await db.commit()
    asyncio.run(_drop_console())

    try:
        resp = client.get("/api/usage/by-client?days=1")
        assert resp.status_code == 200
        body = resp.json()
        client_ids = {it["api_client_id"] for it in body["items"]}
        assert client_ids == {"partner-a", "partner-b"}
        # Console bucket should NOT appear (no Console runs in window)
        assert "console" not in client_ids
    finally:
        # restore the dropped rows so other tests in this module are unaffected
        async def _restore():
            async with AsyncSessionLocal() as db:
                for run_id, cost, lat in [("run-g8-5", 0.01, 1500), ("run-g8-6", 0.02, 1800)]:
                    db.add(RunHistoryModel(
                        organization_id="org_default1",
                        run_id=run_id,
                        agent_id="medical-coding-agent",
                        api_client_id=None,
                        user_id="u-test-bypass",
                        cost_usd=cost,
                        latency_ms=lat,
                        runtime_mode="corti_like_fast",
                        status="COMPLETED",
                        created_at=datetime.now(UTC),
                        tenancy_classification="MODERN",
                    ))
                await db.commit()
        asyncio.run(_restore())
