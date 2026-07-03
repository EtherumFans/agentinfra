"""Pytest test for the schema drift checker.

Spins up an in-memory SQLite DB at the alembic head, then asserts the ORM
declarations match the DB schema with 0 divergences. This catches future
drift at CI time — any time someone adds a column to the ORM model
without a migration (or vice versa), this test fails.
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
    """The ORM declarations must match a fresh `alembic upgrade head` DB."""
    from app.services.schema_drift_service import check_drift

    # Use a temp SQLite DB so we don't touch the dev DB
    db_path = tmp_path / "drift_check.db"
    # Forward slashes — SQLAlchemy URLs are always slash-separated, even on Windows
    db_path_str = str(db_path).replace("\\", "/")
    # Async URL — alembic env.py uses create_async_engine(settings.DATABASE_URL)
    async_db_url = f"sqlite+aiosqlite:///{db_path_str}"
    # Sync URL — check_drift uses sqlalchemy.create_engine (sync)
    sync_db_url = f"sqlite:///{db_path_str}"

    # Run alembic upgrade head against the temp DB.
    # Pydantic Settings honors env var `DATABASE_URL` (same name as field),
    # overriding .env and the hardcoded default.
    env = os.environ.copy()
    env["DATABASE_URL"] = async_db_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # Check drift
    report = check_drift(sync_db_url)

    if report.total > 0:
        lines = [f"Schema drift detected ({report.total} divergences):"]
        for d in report.divergences:
            lines.append(
                f"  [{d.type}] {d.table}.{d.column}  "
                f"ORM={d.orm_value}  DB={d.db_value}"
            )
        pytest.fail("\n".join(lines))


def test_drift_checker_detects_missing_column(tmp_path):
    """Sanity check: if we drop a column from the DB, the checker should flag it."""
    from app.services.schema_drift_service import check_drift
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "missing_col.db"
    db_path_str = str(db_path).replace("\\", "/")
    async_db_url = f"sqlite+aiosqlite:///{db_path_str}"
    sync_db_url = f"sqlite:///{db_path_str}"

    # Run alembic to set up the schema
    env = os.environ.copy()
    env["DATABASE_URL"] = async_db_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    # Drop a column that the ORM declares (e.g. users.department)
    engine = create_engine(sync_db_url)
    with engine.connect() as conn:
        # SQLite doesn't support DROP COLUMN directly — use batch via raw SQL
        # Easier: rename the column to break the ORM match
        conn.execute(text("ALTER TABLE users RENAME COLUMN department TO department_renamed"))
        conn.commit()
    engine.dispose()

    report = check_drift(sync_db_url)
    # We expect at least one divergence related to users.department
    dept_divergences = [d for d in report.divergences if d.table == "users" and d.column == "department"]
    assert len(dept_divergences) >= 1, (
        f"Expected drift on users.department after rename, got: "
        f"{[d.type for d in report.divergences if d.table == 'users']}"
    )
