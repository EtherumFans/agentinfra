"""Phase 5 A3 (2026-07-10) — /usage summary wired to run_history.cost.

Verifies the P1-1 (GAP-12-01) gap closed in Phase 5 A3:

  Before A3: ``GET /api/usage/summary`` aggregated ``Transaction.amount``
  (billing-side debits) as ``credits_used``. Because most agent runs don't
  create debit transactions (only manual top-ups + signup bonus do), the
  page always showed ¥0.00 — even when ``run_history`` had rows with
  non-zero ``cost_usd``.

  After A3: the endpoint aggregates ``run_history.cost_usd`` so the page
  surfaces real LLM cost from agent runs. A ``daily_breakdown`` field is
  also returned to enable A6's 30-day cost chart on the frontend.

Test strategy: insert a row directly into ``run_history`` with a known
non-zero cost, then verify the summary endpoint surfaces it. (We don't
exercise the LLM call here — that path is covered by Phase 4-F3 smoke
tests + ``test_llm_cost_computation.py``.)
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def _sync_db_url() -> str:
    from app.config import settings
    db_url = getattr(settings, "DATABASE_URL", "") or "sqlite+aiosqlite:///./data/icoder.db"
    return db_url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite")


def _insert_run_history_row(
    *,
    run_id: str,
    agent_id: str,
    cost_usd: float,
    user_id: str,
    org_id: str | None = None,
    created_at_iso: str | None = None,
) -> None:
    """Insert one row directly into run_history for test setup."""
    now_iso = created_at_iso or datetime.now(timezone.utc).isoformat()
    engine = create_engine(_sync_db_url(), echo=False)
    try:
        with Session(engine) as session:
            session.execute(
                text("""
                    INSERT INTO run_history
                        (id, organization_id, user_id, agent_id, run_id, trace_id,
                         runtime_mode, latency_ms, cost_usd, input_text,
                         output_summary, error, error_reason, created_at, updated_at)
                    VALUES
                        (:id, :org_id, :user_id, :agent_id, :run_id, :trace_id,
                         :runtime_mode, :latency_ms, :cost_usd, :input_text,
                         :output_summary, :error, :error_reason,
                         :created_at, :created_at)
                """),
                {
                    "id": secrets.token_hex(6),
                    "org_id": org_id,
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "trace_id": "",
                    "runtime_mode": "a2a_pure_llm",
                    "latency_ms": 1234,
                    "cost_usd": cost_usd,
                    "input_text": "test input for usage summary",
                    "output_summary": "test output for usage summary",
                    "error": 0,
                    "error_reason": None,
                    "created_at": now_iso,
                },
            )
            session.commit()
    finally:
        engine.dispose()


def _get_test_user_id(client: TestClient) -> str:
    """The dev auth bypass (ICODER_DISABLE_AUTH_FOR_TESTS=1) installs a
    mock user with stable id ``u-test-bypass`` (see conftest._make_mock_user).
    We don't query an endpoint — we just return that id.

    Note: ``/api/users/me`` returns 404 in the test client because the dev
    auth bypass installs the user via dependency override, not via a real
    session lookup. The id is stable, so direct DB insertion is safe.
    """
    return "u-test-bypass"


# ── A3 #1 — /usage/summary surfaces run_history cost ───────────────────────


def test_a3_usage_summary_includes_run_history_cost(client: TestClient) -> None:
    """``credits_used`` must reflect runs in run_history, not Transaction debits.

    Before A3: this would always be 0 because no Transaction debit rows exist
    for agent runs. After A3: it must equal the sum of run_history.cost_usd.
    """
    user_id = _get_test_user_id(client)
    run_id = f"a3-test-{secrets.token_hex(4)}"
    test_cost = 0.042185  # a realistic per-run LLM cost

    _insert_run_history_row(
        run_id=run_id,
        agent_id="evidence-extractor",
        cost_usd=test_cost,
        user_id=user_id,
    )

    try:
        resp = client.get("/api/usage/summary", params={"days": 7})
        assert resp.status_code == 200, (
            f"GET /api/usage/summary failed: {resp.status_code} {resp.text[:300]}"
        )
        data = resp.json()
        # credits_used must include the row we just inserted (allow for some
        # float slack; the value is rounded to 6 decimal places by the API).
        assert data["credits_used"] >= test_cost - 1e-6, (
            f"expected credits_used >= {test_cost}, got {data['credits_used']}"
        )
        # The currency field is now explicitly returned (Phase 5 A2).
        assert data["currency"] == "CNY", (
            f"expected currency=CNY, got {data.get('currency')!r}"
        )
    finally:
        # Cleanup: delete the row we inserted so subsequent tests aren't polluted.
        engine = create_engine(_sync_db_url(), echo=False)
        try:
            with Session(engine) as session:
                session.execute(
                    text("DELETE FROM run_history WHERE run_id = :rid"),
                    {"rid": run_id},
                )
                session.commit()
        finally:
            engine.dispose()


# ── A3 #2 — /usage/summary returns daily_breakdown ─────────────────────────


def test_a3_usage_summary_returns_daily_breakdown(client: TestClient) -> None:
    """``daily_breakdown`` must be a list of {date, cost} entries for A6's chart."""
    user_id = _get_test_user_id(client)
    run_id = f"a3-daily-{secrets.token_hex(4)}"
    today_iso = datetime.now(timezone.utc).isoformat()
    today_date = today_iso[:10]  # YYYY-MM-DD

    _insert_run_history_row(
        run_id=run_id,
        agent_id="evidence-extractor",
        cost_usd=0.031,
        user_id=user_id,
        created_at_iso=today_iso,
    )

    try:
        resp = client.get("/api/usage/summary", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert "daily_breakdown" in data, (
            f"daily_breakdown missing from response: keys={list(data.keys())}"
        )
        assert isinstance(data["daily_breakdown"], list), (
            f"daily_breakdown must be a list, got: {type(data['daily_breakdown'])}"
        )
        # Today's entry must include the row we just inserted.
        today_entries = [d for d in data["daily_breakdown"] if d["date"] == today_date]
        assert today_entries, (
            f"no entry for today ({today_date}) in daily_breakdown: "
            f"{data['daily_breakdown']}"
        )
        assert today_entries[0]["cost"] >= 0.031 - 1e-6, (
            f"expected today's cost >= 0.031, got {today_entries[0]['cost']}"
        )
    finally:
        engine = create_engine(_sync_db_url(), echo=False)
        try:
            with Session(engine) as session:
                session.execute(
                    text("DELETE FROM run_history WHERE run_id = :rid"),
                    {"rid": run_id},
                )
                session.commit()
        finally:
            engine.dispose()
