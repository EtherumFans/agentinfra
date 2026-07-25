"""Pytest test for the schema drift checker.

Spins up an in-memory SQLite DB at the alembic head, then asserts the ORM
declarations match the DB schema with 0 divergences. This catches future
drift at CI time — any time someone adds a column to the ORM model
without a migration (or vice versa), this test fails.

TD-002 fix: the check runs in a subprocess with a fresh Python
interpreter to isolate ORM ``Base.metadata`` from pollution by prior
tests in the same pytest session. Previously, when other tests imported
model modules that modified ``Base.metadata`` (e.g. by adding ad-hoc
columns or tables), the metadata in the parent process was
contaminated, and ``check_drift`` reported spurious divergences against
the fresh alembic DB.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make `app.*` importable
_BACKEND_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_DIR))


def test_no_schema_drift_against_fresh_alembic_db(tmp_path):
    """The ORM declarations must match a fresh `alembic upgrade head` DB.

    Runs both alembic upgrade AND check_drift in a single subprocess so
    ORM ``Base.metadata`` is populated fresh — no pollution from prior
    tests in the parent pytest session.
    """
    db_path = tmp_path / "drift_check.db"
    db_path_str = str(db_path).replace("\\", "/")
    async_db_url = f"sqlite+aiosqlite:///{db_path_str}"
    sync_db_url = f"sqlite:///{db_path_str}"

    # Inline script: alembic upgrade head + check_drift in one process.
    script = f"""
import os, sys
sys.path.insert(0, {str(_BACKEND_DIR)!r})
os.environ["DATABASE_URL"] = {async_db_url!r}

# Step 1: alembic upgrade head
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd={str(_BACKEND_DIR)!r},
    env={{**os.environ, "DATABASE_URL": {async_db_url!r}}},
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("ALEMBIC_FAIL_STDOUT:", result.stdout)
    print("ALEMBIC_FAIL_STDERR:", result.stderr)
    sys.exit(2)

# Step 2: check_drift (fresh import — Base.metadata is clean)
from app.services.schema_drift_service import check_drift
report = check_drift({sync_db_url!r})
if report.total > 0:
    print("DRIFT_COUNT:", report.total)
    for d in report.divergences:
        print(f"DRIFT [{{d.type}}] {{d.table}}.{{d.column}}  ORM={{d.orm_value}}  DB={{d.db_value}}")
    sys.exit(1)
print("DRIFT_OK: 0 divergences")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"schema drift check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    # Sanity-check the success marker is present
    assert "DRIFT_OK: 0 divergences" in result.stdout, (
        f"Expected DRIFT_OK marker, got:\n{result.stdout}\n{result.stderr}"
    )


def test_drift_checker_detects_missing_column(tmp_path):
    """Sanity check: if we drop a column from the DB, the checker should flag it.

    Runs alembic + ALTER + check_drift in a single subprocess so ORM
    ``Base.metadata`` is populated fresh — no pollution from prior tests
    in the parent pytest session. A1B-AE-RV.6 added the subprocess wrapper
    because RV.3's expanded model imports made the parent-process metadata
    noisy enough to mask the expected users.department divergence.
    """
    db_path = tmp_path / "missing_col.db"
    db_path_str = str(db_path).replace("\\", "/")
    async_db_url = f"sqlite+aiosqlite:///{db_path_str}"
    sync_db_url = f"sqlite:///{db_path_str}"

    script = f"""
import os, sys
sys.path.insert(0, {str(_BACKEND_DIR)!r})
os.environ["DATABASE_URL"] = {async_db_url!r}

# Step 1: alembic upgrade head
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd={str(_BACKEND_DIR)!r},
    env={{**os.environ, "DATABASE_URL": {async_db_url!r}}},
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("ALEMBIC_FAIL_STDOUT:", result.stdout)
    print("ALEMBIC_FAIL_STDERR:", result.stderr)
    sys.exit(2)

# Step 2: rename users.department to break ORM match
from sqlalchemy import create_engine, text
engine = create_engine({sync_db_url!r})
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE users RENAME COLUMN department TO department_renamed"))
    conn.commit()
engine.dispose()

# Step 3: check_drift (fresh import — Base.metadata is clean)
from app.services.schema_drift_service import check_drift
report = check_drift({sync_db_url!r})
dept_divergences = [d for d in report.divergences if d.table == "users" and d.column == "department"]
if len(dept_divergences) < 1:
    types = [d.type for d in report.divergences if d.table == 'users']
    print("NO_DRIFT_DETECTED; user-table divergences:", types)
    sys.exit(1)
print("DRIFT_OK: users.department divergence detected")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"drift detection failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    assert "DRIFT_OK: users.department divergence detected" in result.stdout, (
        f"Expected DRIFT_OK marker, got:\n{result.stdout}\n{result.stderr}"
    )
