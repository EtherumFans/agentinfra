"""Phase 5 A6 (2026-07-10) — /runs/history days filter.

Verifies GAP-12-02 (Phase 4-H §12): the run history endpoint must accept a
``days`` query parameter so the frontend dropdown can filter by 7d / 30d /
all time. Before A6, the endpoint accepted only ``agent_id`` + ``limit``.

Test strategy:
  1. Insert two rows into run_history — one recent (today), one old (60d ago).
  2. Query with days=0 — both rows visible.
  3. Query with days=30 — only today's row visible.
  4. Query with days=7  — only today's row visible.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

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
    user_id: str,
    created_at_iso: str,
    cost_usd: float = 0.001,
) -> None:
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
                    "org_id": None,
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                    "trace_id": "",
                    "runtime_mode": "a2a_pure_llm",
                    "latency_ms": 1234,
                    "cost_usd": cost_usd,
                    "input_text": f"test input for {run_id}",
                    "output_summary": f"test output for {run_id}",
                    "error": 0,
                    "error_reason": None,
                    "created_at": created_at_iso,
                },
            )
            session.commit()
    finally:
        engine.dispose()


def _cleanup(run_ids: list[str]) -> None:
    if not run_ids:
        return
    engine = create_engine(_sync_db_url(), echo=False)
    try:
        with Session(engine) as session:
            for rid in run_ids:
                session.execute(
                    text("DELETE FROM run_history WHERE run_id = :rid"),
                    {"rid": rid},
                )
            session.commit()
    finally:
        engine.dispose()


def _get_test_user_id() -> str:
    """Stable mock user id installed by dev auth bypass (conftest._make_mock_user)."""
    return "u-test-bypass"


def test_a6_runs_history_days_filter(client: TestClient) -> None:
    """`days` parameter must filter rows by created_at >= now - days."""
    user_id = _get_test_user_id()
    today_iso = datetime.now(timezone.utc).isoformat()
    old_iso = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    today_run = f"a6-today-{secrets.token_hex(4)}"
    old_run = f"a6-old-{secrets.token_hex(4)}"
    agent_id = "evidence-extractor"

    _insert_run_history_row(
        run_id=today_run,
        agent_id=agent_id,
        user_id=user_id,
        created_at_iso=today_iso,
    )
    _insert_run_history_row(
        run_id=old_run,
        agent_id=agent_id,
        user_id=user_id,
        created_at_iso=old_iso,
    )

    try:
        # days=0 (no filter) — both rows visible
        resp_all = client.get(
            "/api/runtime/runs/history",
            params={"agent_id": agent_id, "limit": 50, "days": 0},
        )
        assert resp_all.status_code == 200
        all_ids = [it["run_id"] for it in resp_all.json().get("items", [])]
        assert today_run in all_ids
        assert old_run in all_ids

        # days=30 — only today's row visible
        resp_30 = client.get(
            "/api/runtime/runs/history",
            params={"agent_id": agent_id, "limit": 50, "days": 30},
        )
        assert resp_30.status_code == 200
        ids_30 = [it["run_id"] for it in resp_30.json().get("items", [])]
        assert today_run in ids_30, f"today's run missing from 30d filter: {ids_30}"
        assert old_run not in ids_30, (
            f"60-day-old run leaked through 30d filter: {ids_30}"
        )

        # days=7 — only today's row visible
        resp_7 = client.get(
            "/api/runtime/runs/history",
            params={"agent_id": agent_id, "limit": 50, "days": 7},
        )
        assert resp_7.status_code == 200
        ids_7 = [it["run_id"] for it in resp_7.json().get("items", [])]
        assert today_run in ids_7
        assert old_run not in ids_7
    finally:
        _cleanup([today_run, old_run])


def test_a6_runs_history_days_default_is_zero(client: TestClient) -> None:
    """When `days` is omitted, behavior matches days=0 (no date filter)."""
    # The endpoint default is `days=0` per the Query() in run_trace.py:104.
    # We don't insert anything; just verify the endpoint doesn't error when
    # days is omitted and returns the same shape as days=0.
    resp_no_days = client.get("/api/runtime/runs/history", params={"limit": 5})
    resp_days_zero = client.get(
        "/api/runtime/runs/history",
        params={"limit": 5, "days": 0},
    )
    assert resp_no_days.status_code == 200
    assert resp_days_zero.status_code == 200
    # Both must return the same items (no date filter applied in either case)
    assert (
        [it["run_id"] for it in resp_no_days.json().get("items", [])]
        == [it["run_id"] for it in resp_days_zero.json().get("items", [])]
    )
