"""Phase A1A Gate 3.7 — DB-level CHECK / UNIQUE constraint tests.

Charter §3.7 coverage:

1. ``run_history.tenancy_classification`` rejects typos / future
   classifications not in the 7-class taxonomy.
2. ``audit_logs.tenancy_classification`` same.
3. ``run_history.trace_capture_status`` rejects values outside
   {PERSISTED, FAILED, FALLBACK_MEMORY}.
4. ``run_trace_events (run_id, step, ts)`` UNIQUE rejects duplicate
   emits for the same triple.
5. Valid values still insert cleanly (regression guard).

These tests bypass the ORM (which would block invalid values via
Python-level classify_modern_write) and write raw SQL so the DB
constraint is the only thing being exercised.
"""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, UTC
from pathlib import Path

import pytest


# ── §1 tenancy_classification CHECK ───────────────────────────────


@pytest.mark.parametrize("bad_cls", [
    "LEGACY_TENANT_KNOWN_TYPO",
    "tenant_unknown",       # wrong case
    "BogusClassification",
    "modern",               # wrong case
    "",
])
def test_run_history_rejects_invalid_classification(tmp_path, bad_cls):
    """CHECK constraint refuses anything outside the 7-class set."""
    db_path = _init_db_with_constraints(tmp_path / "t1.db")
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


@pytest.mark.parametrize("good_cls", [
    "MODERN",
    "MODERN_SYSTEM",
    "LEGACY_TENANT_VERIFIED",
    "LEGACY_TENANT_INFERRED",
    "LEGACY_TENANT_AMBIGUOUS",
    "LEGACY_TENANT_UNKNOWN",
    "LEGACY_TENANT_KNOWN",   # legacy alias, still allowed
    "QUARANTINED",
    None,                    # NULL allowed (pre-Gate-2 rows)
])
def test_run_history_accepts_valid_classification(tmp_path, good_cls):
    db_path = _init_db_with_constraints(tmp_path / "t2.db")
    conn = sqlite3.connect(db_path)
    try:
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
                good_cls,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ── §2 trace_capture_status CHECK ─────────────────────────────────


@pytest.mark.parametrize("bad_status", [
    "PERSIST",       # typo
    "SUCCESS",       # wrong word
    "Bogus",
    "",
])
def test_run_history_rejects_invalid_trace_capture_status(tmp_path, bad_status):
    db_path = _init_db_with_constraints(tmp_path / "t3.db")
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


# ── §3 run_trace_events UNIQUE (run_id, step, ts) ─────────────────


def test_run_trace_events_rejects_duplicate_run_step_ts(tmp_path):
    """Two emits at the same run_id+step+ts must be rejected."""
    db_path = _init_db_with_constraints(tmp_path / "t4.db")
    conn = sqlite3.connect(db_path)
    try:
        run_id = f"r-dup-{secrets.token_hex(4)}"
        step = "ingest"
        ts = 12345.5
        # First insert succeeds
        conn.execute(
            "INSERT INTO run_trace_events "
            "(id, run_id, step, status, ts, duration_ms) "
            "VALUES (?, ?, ?, 'ok', ?, 0)",
            (secrets.token_hex(6), run_id, step, ts),
        )
        conn.commit()
        # Second insert with same (run_id, step, ts) fails
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO run_trace_events "
                "(id, run_id, step, status, ts, duration_ms) "
                "VALUES (?, ?, ?, 'ok', ?, 0)",
                (secrets.token_hex(6), run_id, step, ts),
            )
            conn.commit()
    finally:
        conn.close()


# ── §4 audit_logs CHECK (mirrors run_history) ─────────────────────


def test_audit_logs_rejects_invalid_classification(tmp_path):
    db_path = _init_db_with_constraints(tmp_path / "t5.db")
    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO audit_logs "
                "(id, action, resource_type, status, tenancy_classification) "
                "VALUES (?, 'act', 'rt', 'success', ?)",
                (secrets.token_hex(6), "BogusClass"),
            )
            conn.commit()
    finally:
        conn.close()


# ── Helper: spin up a fresh DB with the same constraints ──────────


def _init_db_with_constraints(db_path: Path) -> str:
    """Build a fresh DB with all Gate 3.7 constraints.

    Uses raw sqlite3 (no SQLAlchemy) so we can DECLARE the CHECK
    + UNIQUE constraints inline with CREATE TABLE — the same
    shape Migration 019 produces.
    """
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
                error_reason VARCHAR(128),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(48) DEFAULT 'COMPLETED',
                cancel_reason VARCHAR(255),
                cancelled_at DATETIME,
                cancelled_by_user_id VARCHAR(64),
                api_client_id VARCHAR(128),
                embedded_app_id VARCHAR(128),
                session_id VARCHAR(64),
                context_id VARCHAR(64),
                request_id VARCHAR(64),
                idempotency_key VARCHAR(255),
                tenancy_classification VARCHAR(32),
                tenancy_attribution_source VARCHAR(64),
                tenancy_attribution_confidence VARCHAR(16),
                tenancy_attribution_migration VARCHAR(8),
                tenancy_attributed_at DATETIME,
                tenancy_original_org_id VARCHAR(12),
                tenancy_candidate_count INTEGER,
                trace_capture_status VARCHAR(16),
                trace_capture_failure_reason VARCHAR(255),
                CONSTRAINT chk_run_history_tenancy_cls
                    CHECK (tenancy_classification IS NULL OR
                           tenancy_classification IN ({cls_list})),
                CONSTRAINT chk_run_history_trace_cap
                    CHECK (trace_capture_status IS NULL OR
                           trace_capture_status IN
                           ('PERSISTED', 'FAILED', 'FALLBACK_MEMORY'))
            );

            CREATE TABLE audit_logs (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR(64),
                username VARCHAR(64),
                action VARCHAR(128) NOT NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(64),
                details JSON,
                status VARCHAR(32) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                organization_id VARCHAR(12),
                tenancy_classification VARCHAR(32),
                CONSTRAINT chk_audit_logs_tenancy_cls
                    CHECK (tenancy_classification IS NULL OR
                           tenancy_classification IN ({cls_list}))
            );

            CREATE TABLE run_trace_events (
                id VARCHAR(12) PRIMARY KEY,
                run_id VARCHAR(64) NOT NULL,
                organization_id VARCHAR(12),
                step VARCHAR(32) NOT NULL,
                status VARCHAR(16) DEFAULT 'ok',
                ts FLOAT DEFAULT 0,
                duration_ms FLOAT DEFAULT 0,
                safe_metadata_json JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ux_run_trace_events_run_step_ts
                    UNIQUE (run_id, step, ts)
            );
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path.as_posix()
