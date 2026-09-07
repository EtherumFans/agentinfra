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
§5 PostgreSQL — the live non-superuser gate is maintained in
   tests/integration/test_p1_postgres_rls_attack.py and is executed only when
   its two disposable-database URLs are supplied.

Each sub-check uses a temp DB file under tmp_path so the dev DB at
data/icoder.db is NOT touched.
"""
from __future__ import annotations

import os
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


def _current_alembic_head() -> str:
    """Phase A1D.5 — read the canonical head revision from alembic/versions.

    Stale assertions like ``== "026"`` break whenever a new migration lands.
    Reading the head dynamically from the versions directory keeps the
    test self-healing across migration additions. Same pattern used in
    test_a1b_ae_rv_2_migration_safety.py (A1D.3 fix).
    """
    revision_files = sorted(
        f for f in _VERSIONS_DIR.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("__")
    )
    head_revisions: set[str] = set()
    child_revisions: set[str] = set()
    for rf in revision_files:
        text = rf.read_text(encoding="utf-8")
        rev = None
        down = None
        for line in text.splitlines():
            if line.startswith("revision = "):
                rev = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("down_revision = "):
                down = line.split("=", 1)[1].strip().strip('"').strip("'")
        if rev is not None:
            head_revisions.add(rev)
            if down is not None and down != "None":
                child_revisions.add(down)
    heads = head_revisions - child_revisions
    assert len(heads) == 1, f"expected 1 alembic head, got {heads}"
    return next(iter(heads))


def _previous_revision(target: str) -> str:
    """Phase A1D.5 — find the down_revision of the given revision.

    Used for round-trip tests that need to assert "downgrade -1 lands at
    the previous head" without hardcoding the previous revision id.
    """
    for rf in _VERSIONS_DIR.iterdir():
        if not (rf.is_file() and rf.suffix == ".py" and not rf.name.startswith("__")):
            continue
        text = rf.read_text(encoding="utf-8")
        rev = None
        down = None
        for line in text.splitlines():
            if line.startswith("revision = "):
                rev = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("down_revision = "):
                down = line.split("=", 1)[1].strip().strip('"').strip("'")
        if rev == target:
            assert down is not None and down != "None", (
                f"target revision {target} has no down_revision (it's the root)"
            )
            return down
    raise AssertionError(f"target revision {target} not found in {_VERSIONS_DIR}")


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
    """On a brand-new DB, ``alembic upgrade head`` applies all 25
    migrations and lands at version 025.

    This catches ordering bugs (e.g. Migration 021 references a
    column that Migration 020 didn't add) that wouldn't surface
    on a partially-migrated DB.

    Phase A1A Gate 4.2 advanced head from 020 → 021 by adding
    NOT NULL + CHECK on encounters/documents/cdi_cases.organization_id
    (closes GATE3_015).
    A1B-AE.3 → 022 (expert_registry_provenance).
    A1B-AE.4 → 023 (agent_canonical_key_and_alias).
    A1B-AE-R.1.a → 024 (context_task_refs.state CHECK).
    A1B-AE-R.1.b → 025 (contexts.organization_id for cross-tenant).
    A1B-AE-RV.2 → 026 (contexts.organization_id fail-closed, default dropped).
    """
    db_path = str(tmp_path / "fresh.db")
    result = _run_alembic(db_path, "upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head failed on fresh DB:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert _alembic_version(db_path) == _current_alembic_head()
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
    assert _alembic_version(db_path) == _current_alembic_head()

    # Re-run — alembic should succeed silently (no-op when already at head)
    second = _run_alembic(db_path, "upgrade", "head")
    assert second.returncode == 0, (
        f"second upgrade should be no-op; stderr: {second.stderr}"
    )
    assert _alembic_version(db_path) == _current_alembic_head()


# ────────────────────────────────────────────────────────────────────
# §3 Downgrade/Upgrade round-trip
# ────────────────────────────────────────────────────────────────────


def test_downgrade_upgrade_roundtrip(tmp_path) -> None:
    """026 → 025 → 026 lands at the same schema state.

    A1B-AE-RV.2: head is now 026 (Migration 026 dropped the permanent
    default on contexts.organization_id, making the fail-closed policy
    explicit at the DB layer).
    Downgrade -1 returns to 025 (R.1.b state — column present with
    default 'org_default1') and upgrade head re-applies Migration 026.
    """
    db_path = str(tmp_path / "roundtrip.db")
    head_now = _current_alembic_head()
    prev_now = _previous_revision(head_now)
    up1 = _run_alembic(db_path, "upgrade", "head")
    assert up1.returncode == 0
    assert _alembic_version(db_path) == head_now
    assert _column_exists(db_path, "run_trace_events", "event_id")

    # Downgrade one step → previous head (latest migration reversed)
    down = _run_alembic(db_path, "downgrade", "-1")
    assert down.returncode == 0, (
        f"downgrade -1 failed:\nstdout: {down.stdout}\nstderr: {down.stderr}"
    )
    assert _alembic_version(db_path) == prev_now

    # Upgrade back to head
    up2 = _run_alembic(db_path, "upgrade", "head")
    assert up2.returncode == 0
    assert _alembic_version(db_path) == head_now
    assert _column_exists(db_path, "run_trace_events", "event_id")


def test_a2a_v1_interrupted_state_constraint_roundtrip(tmp_path) -> None:
    """055 accepts only the eight supported A2A states and downgrades cleanly."""
    import sqlite3

    db_path = str(tmp_path / "a2a-v1-states.db")
    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    def _insert(state: str, suffix: str) -> None:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO context_task_refs "
                "(context_id, task_id, state, started_at, completed_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP, NULL)",
                (f"context-{suffix}", f"task-{suffix}", state),
            )

    for index, state in enumerate(
        ("input-required", "auth-required", "rejected"), start=1
    ):
        _insert(state, str(index))
    with pytest.raises(sqlite3.IntegrityError):
        _insert("awaiting-unsafe-unknown-state", "invalid")

    # Target the semantic boundary explicitly. Head may gain newer migrations;
    # ``-1`` would then only reverse the newest unrelated revision and stop
    # before exercising 055's protected downgrade.
    blocked = _run_alembic(db_path, "downgrade", "054")
    assert blocked.returncode != 0
    assert "Cannot downgrade revision 055" in blocked.stderr

    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM context_task_refs")
    downgraded = _run_alembic(db_path, "downgrade", "054")
    assert downgraded.returncode == 0, downgraded.stderr
    with pytest.raises(sqlite3.IntegrityError):
        _insert("input-required", "legacy")

    restored = _run_alembic(db_path, "upgrade", "head")
    assert restored.returncode == 0, restored.stderr
    _insert("input-required", "restored")

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
      2. Downgrade one revision from the current head
      3. Manually create a stale _alembic_tmp_run_history table
      4. Re-run upgrade head — the migration must explicitly recover
         the empty scaffold; Alembic does not drop it automatically.
         Populated shadow tables require separate lossless recovery.
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
    assert _alembic_version(db_path) == _current_alembic_head()
    assert _column_exists(db_path, "run_trace_events", "event_id")


# ────────────────────────────────────────────────────────────────────
# §5 PostgreSQL — live gate is explicit and discoverable
# ────────────────────────────────────────────────────────────────────


def test_postgresql_live_release_gate_is_present() -> None:
    source = (
        _BACKEND_ROOT / "tests" / "integration"
        / "test_p1_postgres_rls_attack.py"
    ).read_text(encoding="utf-8")
    assert "P1_POSTGRES_TEST_DATABASE_URL" in source
    assert "P1_POSTGRES_MIGRATION_DATABASE_URL" in source
    assert "rolsuper, rolbypassrls" in source
    for surface in (
        "Patient", "Trace event", "Trace run", "Usage", "Context",
        "Memory consent", "Memory",
    ):
        assert f'"{surface}"' in source


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
    001 → 002 → ... → 025."""
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

    # Walk back from 025 to the root
    head = "025"
    visited = []
    current = head
    while current is not None:
        assert current in chain, f"missing migration with revision={current!r}"
        visited.append(current)
        current = chain[current]
        # Safety: don't loop forever
        assert len(visited) <= 30, "chain too long — possible cycle"
    # We should have walked through all 26 migrations (including the
    # initial afeb04d02665_001_initial_all_tables.py)
    assert len(visited) >= 25, (
        f"chain too short — only walked {len(visited)} steps: {visited}"
    )
    # Head should be in the visited set
    assert head in visited
