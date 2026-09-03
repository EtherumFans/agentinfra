from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = BACKEND_ROOT / "scripts" / "stage_sqlite_migration.py"
SPEC = importlib.util.spec_from_file_location("stage_sqlite_migration", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _migrate(path: Path, revision: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{path.as_posix()}",
            "ICODER_CREDENTIAL_LLM": "",
            "LLM_PROVIDER": "mock",
            "ICODER_ALLOW_EXTERNAL_LLM": "false",
            "ICODER_DISABLE_NATIVE_MEDCODER": "true",
            "ICODER_DATABASE_SQL_ECHO": "false",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _insert_organization(path: Path, organization_id: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO organizations (id, name, slug, plan, settings, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                organization_id,
                "Preserved organization",
                f"preserved-{organization_id}",
                "free",
                '{"source":"migration-test"}',
                1,
            ),
        )
        connection.commit()


def test_shadow_rebuild_reaches_head_and_preserves_existing_values(tmp_path: Path) -> None:
    source = tmp_path / "source-041.db"
    output = tmp_path / "staged"
    _migrate(source, "041")
    _insert_organization(source, "orgpreserve1")
    source_hash = MODULE._sha256(source)

    report = MODULE.stage_copy_upgrade(source, output, backend_root=BACKEND_ROOT)

    assert report["passed"] is True
    assert report["mode"] == "shadow_rebuild_head_source_read_only"
    assert report["source"]["alembic_revisions"] == ["041"]
    assert report["candidate"]["alembic_revisions"] == [
        MODULE._current_head(BACKEND_ROOT)
    ]
    assert report["schema_drift"]["summary"]["total"] == 0
    assert report["data_preservation_mismatches"] == []
    assert MODULE._sha256(source) == source_hash

    with sqlite3.connect(report["candidate_path"]) as connection:
        row = connection.execute(
            "SELECT name, slug, plan, settings, is_active "
            "FROM organizations WHERE id='orgpreserve1'"
        ).fetchone()
    assert row == (
        "Preserved organization",
        "preserved-orgpreserve1",
        "free",
        '{"source":"migration-test"}',
        1,
    )


def test_orphan_organization_repair_is_explicit_inactive_and_copy_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-orphan-041.db"
    _migrate(source, "041")
    with sqlite3.connect(source) as connection:
        connection.execute(
            "INSERT INTO templates "
            "(id, organization_id, name, description, content, category, "
            "language, is_builtin, scope) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "template0001",
                "missingorg01",
                "Preserved template",
                "synthetic",
                "no clinical content",
                "general",
                "zh-CN",
                0,
                "tenant",
            ),
        )
        connection.commit()
    source_hash = MODULE._sha256(source)

    with pytest.raises(MODULE.ReconciliationError, match="foreign-key violations"):
        MODULE.stage_copy_upgrade(
            source,
            tmp_path / "strict",
            backend_root=BACKEND_ROOT,
        )
    assert not (tmp_path / "strict").exists()

    report = MODULE.stage_copy_upgrade(
        source,
        tmp_path / "quarantined",
        backend_root=BACKEND_ROOT,
        quarantine_orphan_organizations=True,
    )

    assert report["passed"] is True
    assert len(report["quarantine_repairs"]) == 1
    assert report["quarantine_repairs"][0]["referencing_rows"] == 1
    assert report["candidate"]["foreign_key_violation_count"] == 0
    assert MODULE._sha256(source) == source_hash
    with sqlite3.connect(report["candidate_path"]) as connection:
        parent = connection.execute(
            "SELECT is_active, settings FROM organizations WHERE id='missingorg01'"
        ).fetchone()
        child = connection.execute(
            "SELECT name, organization_id FROM templates WHERE id='template0001'"
        ).fetchone()
    assert parent is not None
    assert parent[0] == 0
    assert "quarantined_missing_parent" in parent[1]
    assert child == ("Preserved template", "missingorg01")


def test_inspection_is_read_only_and_reports_safe_fk_aggregates(tmp_path: Path) -> None:
    source = tmp_path / "inspect-041.db"
    _migrate(source, "041")
    source_hash = MODULE._sha256(source)

    report = MODULE.inspect_database(source)

    assert report["integrity_check"] == "ok"
    assert report["alembic_revisions"] == ["041"]
    assert report["foreign_key_violation_count"] == 0
    assert report["missing_organization_parents"] == []
    assert MODULE._sha256(source) == source_hash
