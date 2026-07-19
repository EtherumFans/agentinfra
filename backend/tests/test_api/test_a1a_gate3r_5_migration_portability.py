"""Phase A1A Gate 3R.5 — Migration portability + interrupted recovery.

Charter §3R.5: verify Migration 020 is portable across DB states
and recovers cleanly from interruption. The charter names four
sub-checks; PostgreSQL verification is environment-blocked per
Gate 3R.0 §19 and emits a partial verdict.

§1 Fresh SQLite — apply all migrations head-to-tail on a brand-new DB
§2 Existing SQLite — apply 020 on top of the dev DB (already done
   in Gate 3R.4); verify idempotent re-run is a no-op
§3 Downgrade/Upgrade round-trip — 020 → 019 → 020 lands at the same
   state (modulo the backfill, which is irreversible for the
   canonicalized PERSISTED rows)
§4 Interrupted recovery — simulate a mid-migration crash and verify
   the next `alembic upgrade head` completes cleanly
§5 PostgreSQL — BLOCKED (no psql/asyncpg/testcontainers available;
   see Gate 3R.0 §19). Partial verdict.

Each sub-check uses a temp DB file under tmp_path so the dev DB at
data/icoder.db is NOT touched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# Absolute path to the backend root (where alembic.ini lives).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"
_VERSIONS_DIR = _BACKEND_ROOT / "alembic" / "versions"


def _run_alembic(target_db: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke ``python -m alembic`` against ``target_db``.

    Sets DATABASE_URL via env so alembic reads the override instead
    of the alembic.ini default (which points at data/icoder.db).
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{target_db}"
    # Make sure backend root is on sys.path so migration modules
    # can import app.* if they need to.
    env["PYTHONPATH"] = str(_BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args]
    return subprocess.run(
        cmd,
        cwd=str(_BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _column_exists(db_path: str, table: str, column: str) -> bool:
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(row[1] == column for row in rows)
    finally:
        conn.close()


def _alembic_version(db_path: str) -> str:
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        conn.close()


def _count_trace_capture_status(db_path: str, status: str) -> int:
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM run_history WHERE trace_capture_status = ?",
            (status,),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


# ────────────────────────────────────────────────────────────────────
# §1 Fresh SQLite — apply all migrations head-to-tail
# ────────────────────────────────────────────────────────────────────


def test_fresh_sqlite_applies_all_migrations_to_head(tmp_path) -> None:
    """On a brand-new DB, ``alembic upgrade head`` applies all 20
    migrations and lands at version 020.

    This catches ordering bugs (e.g. Migration 020 references a
    column that Migration 019 didn't add) that wouldn't surface
    on a partially-migrated DB.
    """
    db_path = str(tmp_path / "fresh.db")
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head failed on fresh DB:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _alembic_version(db_path) == "020"
    # Verify the new columns landed
    assert _column_exists(db_path, "run_trace_events", "event_id")
    assert _column_exists(db_path, "run_trace_events", "sequence_number")
    assert _column_exists(db_path, "run_trace_events", "trace_id")
    assert _column_exists(db_path, "run_trace_events", "identity_source")


# ────────────────────────────────────────────────────────────────────
# §2 Existing SQLite — idempotent re-run
# ────────────────────────────────────────────────────────────────────


def test_migration_020_idempotent_rerun(tmp_path) -> None:
    """Running ``alembic upgrade head`` twice on the same DB is a
    no-op the second time (alembic knows the version is already head)."""
    db_path = str(tmp_path / "existing.db")
    first = _run_alembic(db_path, "upgrade", "head")
    assert first.returncode == 0
    assert _alembic_version(db_path) == "020"

    # Re-run — alembic should succeed silently (no-op when already at head)
    second = _run_alembic(db_path, "upgrade", "head")
    assert second.returncode == 0, (
        f"second upgrade should be no-op; stderr: {second.stderr}"
    )
    assert _alembic_version(db_path) == "020"


# ────────────────────────────────────────────────────────────────────
# §3 Downgrade/Upgrade round-trip
# ────────────────────────────────────────────────────────────────────


def test_downgrade_upgrade_roundtrip(tmp_path) -> None:
    """020 → 019 → 020 lands at the same schema state.

    Downgrade drops the 4 new columns + narrows the CHECK; upgrade
    re-adds them. The backfill (NULL → NEVER_CAPTURED_LEGACY) is
    NOT round-trip-preserving on the dev DB because the downgrade
    reverts backfilled rows to NULL. We verify column presence +
    alembic version only, not row state.
    """
    db_path = str(tmp_path / "roundtrip.db")
    up1 = _run_alembic(db_path, "upgrade", "head")
    assert up1.returncode == 0
    assert _alembic_version(db_path) == "020"
    assert _column_exists(db_path, "run_trace_events", "event_id")

    # Downgrade one step → 019
    down = _run_alembic(db_path, "downgrade", "-1")
    assert down.returncode == 0, (
        f"downgrade -1 failed:\nstdout: {down.stdout}\nstderr: {down.stderr}"
    )
    assert _alembic_version(db_path) == "019"
    # Columns should be gone
    assert not _column_exists(db_path, "run_trace_events", "event_id")
    assert not _column_exists(db_path, "run_trace_events", "sequence_number")

    # Upgrade back to head → 020
    up2 = _run_alembic(db_path, "upgrade", "head")
    assert up2.returncode == 0
    assert _alembic_version(db_path) == "020"
    assert _column_exists(db_path, "run_trace_events", "event_id")


# ────────────────────────────────────────────────────────────────────
# §4 Interrupted recovery — simulate mid-migration crash
# ────────────────────────────────────────────────────────────────────


def test_interrupted_recovery_completes_on_retry(tmp_path) -> None:
    """If alembic is interrupted mid-migration (process killed, DB
    locked), the next ``alembic upgrade head`` must complete cleanly.

    SQLite + batch_alter_table creates a temp table `_alembic_tmp_*`
    during CHECK constraint changes. If the process is killed at
    that moment, the temp table lingers and the next migration
    attempt may fail. Gate 3 ran into this during Migration 019
    and had to drop the temp table manually.

    We simulate this by:
      1. Upgrade to head
      2. Downgrade to 019
      3. Manually create a stale _alembic_tmp_run_history table
      4. Re-run upgrade head — must succeed (the migration code
         doesn't explicitly handle this; alembic's batch_alter_table
         DROP IF EXISTS handles it automatically)
    """
    db_path = str(tmp_path / "interrupted.db")
    up1 = _run_alembic(db_path, "upgrade", "head")
    assert up1.returncode == 0
    down = _run_alembic(db_path, "downgrade", "-1")
    assert down.returncode == 0

    # Simulate the stale temp table from an interrupted batch_alter_table
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        # Create a leftover temp table that would block batch_alter_table
        conn.execute(
            "CREATE TABLE _alembic_tmp_run_history AS "
            "SELECT * FROM run_history WHERE 1=0"
        )
        conn.commit()
    finally:
        conn.close()

    # Recovery: re-run upgrade head
    recovery = _run_alembic(db_path, "upgrade", "head")
    assert recovery.returncode == 0, (
        f"recovery upgrade failed:\nstdout: {recovery.stdout}\n"
        f"stderr: {recovery.stderr}"
    )
    assert _alembic_version(db_path) == "020"
    assert _column_exists(db_path, "run_trace_events", "event_id")


# ────────────────────────────────────────────────────────────────────
# §5 PostgreSQL — BLOCKED (partial verdict)
# ────────────────────────────────────────────────────────────────────


def test_postgresql_migration_verification_blocked() -> None:
    """Document the partial verdict: PostgreSQL migration portability
    is NOT verified because no PG tooling is installed in this env.

    Charter §3R.5 permits the partial verdict
    PARTIAL_BLOCKED_BY_POSTGRES_MIGRATION_NOT_VERIFIED. This test
    exists primarily to surface the gap in the test suite output
    so it's not silently forgotten.
    """
    blockers = []
    # Check for psql CLI
    if shutil.which("psql") is None:
        blockers.append("psql CLI not installed")
    # Check for asyncpg / psycopg
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        blockers.append("asyncpg not installed")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        blockers.append("psycopg not installed")
    try:
        import testcontainers  # noqa: F401
    except ImportError:
        blockers.append("testcontainers not installed")

    # If everything is installed, this test would normally run a real
    # PG verification — but for now, just assert we know what's missing.
    assert blockers, (
        "PG tooling IS installed — this test should be promoted to "
        "actually run the migration against a real PG instance. "
        "Remove the partial verdict in Gate 3R.5 closure report."
    )
    # The verdict: PG verification is blocked.
    # Document the blockers as the test's failure mode (which is
    # actually the expected state).
    assert "psql CLI not installed" in blockers


# ────────────────────────────────────────────────────────────────────
# §6 All migration files load cleanly
# ────────────────────────────────────────────────────────────────────


def test_all_migrations_have_unique_revisions() -> None:
    """Every migration file has a unique revision ID."""
    import re
    revisions = []
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        m = re.search(r'^revision[^=]*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m, f"could not find revision= in {path.name}"
        revisions.append((m.group(1), path.name))
    # Check uniqueness
    seen = {}
    for rev, name in revisions:
        assert rev not in seen, (
            f"duplicate revision {rev!r} in {name} and {seen[rev]}"
        )
        seen[rev] = name


def test_migration_chain_is_contiguous() -> None:
    """The down_revision chain forms a single linear sequence
    001 → 002 → ... → 020."""
    import re
    chain = {}  # revision → down_revision
    for path in sorted(_VERSIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        rev_m = re.search(r'^revision[^=]*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        down_m = re.search(r'^down_revision[^=]*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert rev_m, f"missing revision in {path.name}"
        # Some migrations use None as down_revision (the initial one)
        down = down_m.group(1) if down_m else None
        chain[rev_m.group(1)] = down

    # Walk back from 020 to the root
    head = "020"
    visited = []
    current = head
    while current is not None:
        assert current in chain, f"missing migration with revision={current!r}"
        visited.append(current)
        current = chain[current]
        # Safety: don't loop forever
        assert len(visited) <= 30, "chain too long — possible cycle"
    # We should have walked through all 21 migrations (including the
    # initial afeb04d02665_001_initial_all_tables.py)
    assert len(visited) >= 20, (
        f"chain too short — only walked {len(visited)} steps: {visited}"
    )
    # Head should be in the visited set
    assert head in visited
