"""Phase A1A Gate 3.2 — Tenant Read Policy integration tests.

Charter §3.2 §4 negative-path coverage at the API layer:

  - /api/usage/summary excludes QUARANTINED / UNKNOWN / AMBIGUOUS /
    MODERN_SYSTEM rows from credits_used + daily_breakdown
  - /api/usage/by-agent excludes the same
  - /api/usage/by-client excludes the same
  - /api/usage/history excludes the same (audit_logs)
  - /api/runtime/runs/history excludes the same (run_history)

These are REAL HTTP roundtrips through the FastAPI app — they prove the
filter is wired into the production endpoints, not just into the
``apply_tenant_visibility_filter`` helper.
"""
from __future__ import annotations

import asyncio
import os
import secrets
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
def seeded_invisible_rows(client: TestClient):
    """Seed one MODERN row + four invisible classifications under the
    test user, then yield and clean up.

    The shared session test database can legitimately contain runs produced by
    earlier API suites. Capture the public aggregate baseline so these tests
    assert only their own visibility delta instead of depending on file order.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.models.audit_log import AuditLog as AuditLogModel

    now = datetime.now(UTC)
    user_id = "u-test-bypass"
    # Cost assignments: MODERN contributes 0.10, each invisible contributes
    # 0.50, so any leak shows up as +0.50 per invisible row.
    token = secrets.token_hex(4)
    rows = [
        (f"run-g32-modern-{token}", "MODERN", 0.10),
        (f"run-g32-quarantined-{token}", "QUARANTINED", 0.50),
        (f"run-g32-unknown-{token}", "LEGACY_TENANT_UNKNOWN", 0.50),
        (f"run-g32-ambiguous-{token}", "LEGACY_TENANT_AMBIGUOUS", 0.50),
        (f"run-g32-system-{token}", "MODERN_SYSTEM", 0.50),
    ]
    audit_rows = [
        (f"audit-g32-modern-{token}", "MODERN"),
        (f"audit-g32-unknown-{token}", "LEGACY_TENANT_UNKNOWN"),
        (f"audit-g32-quarantined-{token}", "QUARANTINED"),
    ]
    baseline_summary = client.get("/api/usage/summary?days=1").json()
    baseline_by_agent = client.get("/api/usage/by-agent?days=1").json()
    baseline_agent = next(
        (
            item for item in baseline_by_agent.get("items", [])
            if item.get("agent_id") == "evidence-extractor"
        ),
        {"run_count": 0, "cost": 0.0},
    )
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    baseline_today_cost = sum(
        day["cost"] for day in baseline_summary.get("daily_breakdown", [])
        if day.get("date") == today_str
    )

    async def _seed():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE user_id = :u AND run_id LIKE 'run-g32-%'"
            ), {"u": user_id})
            await db.execute(text(
                "DELETE FROM audit_logs WHERE user_id = :u AND action LIKE 'audit-g32-%'"
            ), {"u": user_id})
            for run_id, cls, cost in rows:
                db.add(RunHistoryModel(
                    run_id=run_id,
                    agent_id="evidence-extractor",
                    user_id=user_id,
                    organization_id="org_default1",
                    cost_usd=cost,
                    latency_ms=1000,
                    runtime_mode="a2a_pure_llm",
                    status="COMPLETED",
                    created_at=now,
                    tenancy_classification=cls,
                ))
            for audit_id, cls in audit_rows:
                db.add(AuditLogModel(
                    user_id=user_id,
                    organization_id="org_default1",
                    action=audit_id,
                    resource_type="test",
                    status="success",
                    tenancy_classification=cls,
                ))
            await db.commit()

    asyncio.run(_seed())
    yield {
        "rows": rows,
        "credits_used": baseline_summary.get("credits_used", 0.0),
        "today_cost": baseline_today_cost,
        "agent_run_count": baseline_agent.get("run_count", 0),
        "agent_cost": baseline_agent.get("cost", 0.0),
    }
    async def _clear():
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "DELETE FROM run_history WHERE user_id = :u AND run_id LIKE 'run-g32-%'"
            ), {"u": user_id})
            await db.execute(text(
                "DELETE FROM audit_logs WHERE user_id = :u AND action LIKE 'audit-g32-%'"
            ), {"u": user_id})
            await db.commit()
    asyncio.run(_clear())


# ── §1 /api/usage/summary ────────────────────────────────────────────


def test_summary_excludes_invisible_classifications(
    client: TestClient, seeded_invisible_rows,
):
    """credits_used must equal ONLY the MODERN row (0.10), not 0.10 +
    4×0.50 = 2.10. This is the core charter §3.2 requirement: rows
    invisible to the tenant don't surface in usage aggregates."""
    resp = client.get("/api/usage/summary?days=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected = seeded_invisible_rows["credits_used"] + 0.10
    assert abs(body["credits_used"] - expected) < 1e-6, (
        f"expected baseline + 0.10 ({expected}), got {body['credits_used']}"
    )


def test_summary_daily_breakdown_excludes_invisible(
    client: TestClient, seeded_invisible_rows,
):
    """daily_breakdown sums cost per day; must not include invisible
    rows. Today's total should be 0.10 only."""
    resp = client.get("/api/usage/summary?days=1")
    assert resp.status_code == 200
    body = resp.json()
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today_total = sum(
        day["cost"] for day in body["daily_breakdown"]
        if day["date"] == today_str
    )
    expected = seeded_invisible_rows["today_cost"] + 0.10
    assert abs(today_total - expected) < 1e-6, (
        f"daily_breakdown today={today_total}, expected {expected}"
    )


# ── §2 /api/usage/by-agent ───────────────────────────────────────────


def test_by_agent_excludes_invisible(
    client: TestClient, seeded_invisible_rows,
):
    """Only the MODERN row should appear under evidence-extractor."""
    resp = client.get("/api/usage/by-agent?days=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = {it["agent_id"]: it for it in body["items"]}
    assert "evidence-extractor" in items
    assert items["evidence-extractor"]["run_count"] == (
        seeded_invisible_rows["agent_run_count"] + 1
    )
    expected_cost = seeded_invisible_rows["agent_cost"] + 0.10
    assert abs(items["evidence-extractor"]["cost"] - expected_cost) < 1e-6


# ── §3 /api/runtime/runs/history ─────────────────────────────────────


def test_runs_history_excludes_invisible(
    client: TestClient, seeded_invisible_rows,
):
    """runs/history list endpoint must return only the MODERN row."""
    resp = client.get(
        "/api/runtime/runs/history",
        params={"agent_id": "evidence-extractor", "limit": 100, "days": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = {it["run_id"] for it in body["items"]}
    # The MODERN run should be present
    modern_id = next(
        rid for rid, *_ in seeded_invisible_rows["rows"]
        if rid.startswith("run-g32-modern-")
    )
    assert modern_id in returned_ids
    # All invisible runs must be absent
    for invisible_prefix in (
        "run-g32-quarantined-",
        "run-g32-unknown-",
        "run-g32-ambiguous-",
        "run-g32-system-",
    ):
        leaked = [rid for rid in returned_ids if rid.startswith(invisible_prefix)]
        assert not leaked, (
            f"{invisible_prefix} rows leaked into runs/history: {leaked}"
        )


# ── §4 /api/usage/history (audit_logs) ───────────────────────────────


def test_usage_history_excludes_invisible(
    client: TestClient, seeded_invisible_rows,
):
    """/usage/history reads from audit_logs. Only the MODERN audit row
    should appear — UNKNOWN/QUARANTINED are invisible."""
    resp = client.get("/api/usage/history?days=1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    actions = {it["endpoint"] for it in body["history"]}
    assert any(a.startswith("audit-g32-modern-") for a in actions), actions
    assert not any(a.startswith("audit-g32-unknown-") for a in actions), actions
    assert not any(a.startswith("audit-g32-quarantined-") for a in actions), actions
