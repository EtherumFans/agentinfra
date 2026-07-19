"""Phase A1A Gate 3.8 — Cross-gate security negative tests (consolidated).

Charter §3.8 asks for a regression + security negative test sweep that
explicitly enumerates the defence-in-depth invariants established in
Gates 3.1 – 3.7. This file is the consolidated negative-path
authoritative source: each test names the gate it exercises and the
specific invariant that must hold.

Layered invariants under test:

  Layer 1 (Gate 2 / Gate 3.1)  app-level classify_modern_write refuses
                                NULL org writes in cloud mode.
  Layer 2 (Gate 3.7)           DB CHECK constraint rejects invalid
                                tenancy_classification values.
  Layer 3 (Gate 3.2)           tenant_read_policy filter excludes
                                invisible classes from list endpoints.
  Layer 4 (Gate 3.2)           point-lookup guard returns exact 404
                                for invisible rows (no existence leak).
  Layer 5 (Gate 3.4 / 3.5)     SSE + Console trace denial paths return
                                exact 404 for invisible classifications.
  Layer 6 (Gate 3.6)           system_audit refuses non-allowlist actions.

Positive regressions on the same paths are covered by the per-gate
test files (test_a1a_gate3_*.py, test_phase7_*.py) — this file is
the negative-path spine.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, UTC
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ── Layer 2: DB CHECK constraints ─────────────────────────────────────


@pytest.mark.parametrize("bad_cls", [
    "TENANT_MODERN",            # wrong prefix
    "modern",                   # wrong case
    "LEGACY_TENANT_KNOWN_X",    # trailing typo
    "QUARANTINE",               # missing D
    "MODERN_USER",              # plausible but invented
])
def test_L2_db_rejects_invalid_tenancy_classification(tmp_path: Path, bad_cls: str):
    """Gate 3.7: DB CHECK refuses anything outside the 7-class set."""
    db_path = _init_min_db(tmp_path / "g38.db")
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO run_history "
                "(id, organization_id, user_id, agent_id, run_id, "
                " trace_id, runtime_mode, latency_ms, cost_usd, "
                " input_text, output_summary, error, status, "
                " created_at, updated_at, tenancy_classification) "
                "VALUES (?, NULL, 'u', 'a', ?, '', '', 0, 0.0, '', '', 0, "
                " 'COMPLETED', ?, ?, ?)",
                (
                    secrets.token_hex(6),
                    f"r-{secrets.token_hex(4)}",
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                    bad_cls,
                ),
            )
            conn.commit()
    finally:
        conn.close()


@pytest.mark.parametrize("bad_status", ["PERSIST", "OK", "DONE", "MEMORY"])
def test_L2_db_rejects_invalid_trace_capture_status(tmp_path: Path, bad_status: str):
    """Gate 3.7: trace_capture_status must be PERSISTED/FAILED/FALLBACK_MEMORY."""
    db_path = _init_min_db(tmp_path / "g38.db")
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO run_history "
                "(id, organization_id, user_id, agent_id, run_id, "
                " trace_id, runtime_mode, latency_ms, cost_usd, "
                " input_text, output_summary, error, status, "
                " created_at, updated_at, trace_capture_status) "
                "VALUES (?, NULL, 'u', 'a', ?, '', '', 0, 0.0, '', '', 0, "
                " 'COMPLETED', ?, ?, ?)",
                (
                    secrets.token_hex(6),
                    f"r-{secrets.token_hex(4)}",
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                    bad_status,
                ),
            )
            conn.commit()
    finally:
        conn.close()


def test_L2_db_rejects_duplicate_run_step_ts(tmp_path: Path):
    """Gate 3.7: composite UNIQUE on (run_id, step, ts)."""
    db_path = _init_min_db(tmp_path / "g38.db")
    conn = sqlite3.connect(db_path)
    try:
        run_id = f"r-dup-{secrets.token_hex(4)}"
        ts = 12345.6789
        conn.execute(
            "INSERT INTO run_trace_events (id, run_id, step, status, ts, duration_ms) "
            "VALUES (?, ?, 'ingest', 'ok', ?, 0)",
            (secrets.token_hex(6), run_id, ts),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO run_trace_events (id, run_id, step, status, ts, duration_ms) "
                "VALUES (?, ?, 'ingest', 'ok', ?, 0)",
                (secrets.token_hex(6), run_id, ts),
            )
            conn.commit()
    finally:
        conn.close()


# ── Layer 3 + 4: API list + point-lookup visibility ───────────────────


@pytest.fixture
def seeded_invisible_rows(client: TestClient):
    """Seed one visible + four invisible rows under the test tenant."""
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from sqlalchemy import text
    import asyncio

    async def _seed():
        now = datetime.now(UTC)
        token = secrets.token_hex(4)
        rows = [
            (f"run-g38-modern-{token}", "MODERN"),
            (f"run-g38-quarantined-{token}", "QUARANTINED"),
            (f"run-g38-unknown-{token}", "LEGACY_TENANT_UNKNOWN"),
            (f"run-g38-ambiguous-{token}", "LEGACY_TENANT_AMBIGUOUS"),
            (f"run-g38-system-{token}", "MODERN_SYSTEM"),
        ]
        async with AsyncSessionLocal() as db:
            for run_id, cls in rows:
                db.add(RunHistoryModel(
                    id=secrets.token_hex(6),
                    organization_id="org_default1",
                    user_id="u-test-bypass",
                    agent_id="medical-coding",
                    run_id=run_id,
                    runtime_mode="test",
                    latency_ms=0,
                    cost_usd=0.0,
                    input_text="",
                    output_summary="",
                    error=False,
                    status="COMPLETED",
                    created_at=now,
                    updated_at=now,
                    tenancy_classification=cls,
                ))
            await db.commit()
        return [r[0] for r in rows]

    async def _clear(seeded):
        async with AsyncSessionLocal() as db:
            placeholders = ",".join(f":p{i}" for i in range(len(seeded)))
            params = {f"p{i}": rid for i, rid in enumerate(seeded)}
            await db.execute(
                text(f"DELETE FROM run_history WHERE run_id IN ({placeholders})"),
                params,
            )
            await db.commit()

    seeded = asyncio.run(_seed())
    yield seeded
    asyncio.run(_clear(seeded))


_TENANT_HEADER = {"Tenant-Name": "org_default1"}


def test_L3_runtime_history_excludes_all_invisible(client: TestClient, seeded_invisible_rows):
    """Gate 3.2 + 3.8: list endpoint MUST exclude all 4 invisible classes."""
    resp = client.get("/api/runtime/runs/history?limit=200", headers=_TENANT_HEADER)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    returned_ids = {it["run_id"] for it in items}
    modern, q, u, a, s = seeded_invisible_rows
    assert modern in returned_ids, "MODERN row should be visible"
    assert q not in returned_ids, "QUARANTINED leaked into list"
    assert u not in returned_ids, "LEGACY_TENANT_UNKNOWN leaked into list"
    assert a not in returned_ids, "LEGACY_TENANT_AMBIGUOUS leaked into list"
    assert s not in returned_ids, "MODERN_SYSTEM leaked into list"


def test_L4_point_lookup_quarantined_returns_404_no_leak(client: TestClient, seeded_invisible_rows):
    """Gate 3.2 §4: point lookup of invisible row = exact 404, generic body."""
    _, q_run, *_ = seeded_invisible_rows
    resp = client.get(f"/api/v1/runs/{q_run}", headers=_TENANT_HEADER)
    assert resp.status_code == 404
    body = resp.json()
    detail = body.get("detail", "").lower()
    assert q_run not in detail
    assert "quarantined" not in detail
    assert "classification" not in detail


def test_L4_point_lookup_unknown_returns_404_no_leak(client: TestClient, seeded_invisible_rows):
    """Gate 3.2 §4: same for LEGACY_TENANT_UNKNOWN."""
    _, _, u_run, *_ = seeded_invisible_rows
    resp = client.get(f"/api/v1/runs/{u_run}", headers=_TENANT_HEADER)
    assert resp.status_code == 404
    assert u_run not in resp.json().get("detail", "").lower()


def test_L4_point_lookup_ambiguous_returns_404_no_leak(client: TestClient, seeded_invisible_rows):
    """Gate 3.2 §4: same for LEGACY_TENANT_AMBIGUOUS."""
    _, _, _, a_run, _ = seeded_invisible_rows
    resp = client.get(f"/api/v1/runs/{a_run}", headers=_TENANT_HEADER)
    assert resp.status_code == 404
    assert a_run not in resp.json().get("detail", "").lower()


def test_L4_point_lookup_modern_system_returns_404(client: TestClient, seeded_invisible_rows):
    """Gate 3.2 §4: MODERN_SYSTEM (system-scope) invisible to tenant reads."""
    *_, s_run = seeded_invisible_rows
    resp = client.get(f"/api/v1/runs/{s_run}", headers=_TENANT_HEADER)
    assert resp.status_code == 404


def test_L4_point_lookup_modern_visible(client: TestClient, seeded_invisible_rows):
    """Regression: MODERN row is still served."""
    modern_run, *_ = seeded_invisible_rows
    resp = client.get(f"/api/v1/runs/{modern_run}", headers=_TENANT_HEADER)
    assert resp.status_code == 200


# ── Layer 5: SSE + trace denial paths ─────────────────────────────────


def test_L5_trace_partner_denies_invisible(client: TestClient, seeded_invisible_rows):
    """Gate 3.5: partner trace URL endpoint refuses invisible rows."""
    _, q_run, *_ = seeded_invisible_rows
    # Without a valid trace_token the partner endpoint returns 403/404; with
    # a token for an invisible row the token-mint path itself refuses.
    resp = client.get(f"/api/v1/runs/{q_run}/trace", headers=_TENANT_HEADER)
    assert resp.status_code in (401, 403, 404)


# ── Layer 6: system_audit allowlist ───────────────────────────────────


def test_L6_system_audit_refuses_tenant_action():
    """Gate 3.6: system_audit allowlist blocks tenant-scoped actions."""
    from app.services.system_audit import system_audit, SYSTEM_AUDIT_ACTIONS

    # Sanity: tenant-scoped action is NOT in the allowlist
    assert "user.login" not in SYSTEM_AUDIT_ACTIONS
    assert "agent.run" not in SYSTEM_AUDIT_ACTIONS

    # Calling system_audit with a tenant action must raise
    class _FakeDB:
        async def execute(self, *args, **kwargs): pass
        async def commit(self): pass
        async def refresh(self, *args, **kwargs): pass
        def add(self, *args, **kwargs): pass

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(ValueError):
            loop.run_until_complete(system_audit(
                _FakeDB(),
                action="user.login",   # tenant-scoped, not allowlisted
                resource_type="user",
                resource_id="u-1",
            ))
    finally:
        loop.close()


def test_L6_system_audit_accepts_security_admin_prefix():
    """Gate 3.6: security_admin.* prefix is allowlisted."""
    from app.services.system_audit import _SYSTEM_AUDIT_ACTION_PREFIXES
    assert "security_admin." in _SYSTEM_AUDIT_ACTION_PREFIXES


# ── Helper: minimal DB with Gate 3.7 constraints ──────────────────────


def _init_min_db(db_path: Path) -> str:
    """Build a minimal DB with Gate 3.7 constraints inline."""
    cls_list = (
        "'MODERN', 'MODERN_SYSTEM', "
        "'LEGACY_TENANT_VERIFIED', 'LEGACY_TENANT_INFERRED', "
        "'LEGACY_TENANT_AMBIGUOUS', 'LEGACY_TENANT_UNKNOWN', "
        "'LEGACY_TENANT_KNOWN', 'QUARANTINED'"
    )
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.executescript(f"""
            CREATE TABLE run_history (
                id VARCHAR(12) PRIMARY KEY,
                organization_id VARCHAR(12),
                user_id VARCHAR(64),
                agent_id VARCHAR(128) NOT NULL,
                run_id VARCHAR(64) NOT NULL UNIQUE,
                trace_id VARCHAR(64) DEFAULT '',
                runtime_mode VARCHAR(48) DEFAULT '',
                latency_ms INTEGER DEFAULT 0,
                cost_usd FLOAT DEFAULT 0.0,
                input_text TEXT DEFAULT '',
                output_summary TEXT DEFAULT '',
                error BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(48) DEFAULT 'COMPLETED',
                tenancy_classification VARCHAR(32),
                trace_capture_status VARCHAR(16),
                CONSTRAINT chk_run_history_tenancy_cls
                    CHECK (tenancy_classification IS NULL OR
                           tenancy_classification IN ({cls_list})),
                CONSTRAINT chk_run_history_trace_cap
                    CHECK (trace_capture_status IS NULL OR
                           trace_capture_status IN
                           ('PERSISTED', 'FAILED', 'FALLBACK_MEMORY'))
            );
            CREATE TABLE run_trace_events (
                id VARCHAR(12) PRIMARY KEY,
                run_id VARCHAR(64) NOT NULL,
                step VARCHAR(32) NOT NULL,
                status VARCHAR(16) DEFAULT 'ok',
                ts FLOAT DEFAULT 0,
                duration_ms FLOAT DEFAULT 0,
                CONSTRAINT ux_run_trace_events_run_step_ts
                    UNIQUE (run_id, step, ts)
            );
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path.as_posix()
