"""Stage an Alembic upgrade on a consistent copy of a local SQLite database.

The source database is opened read-only and is never migrated, replaced, or
deleted.  The default command is inspection-only.  ``--stage-copy-upgrade``
creates a consistent SQLite snapshot, builds a separate clean database at the
current Alembic head, copies all source tables into that clean schema, and
proves that every pre-existing table/column value is unchanged by comparing
PHI-safe digests rather than exporting row content.  The shadow rebuild is
deliberate: a legacy database may contain future tables created by ORM
``create_all`` even while its Alembic revision is behind, so in-place migration
would collide with those tables.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class ReconciliationError(RuntimeError):
    """Raised when a staged migration cannot be proven safe."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def _alembic_revisions(connection: sqlite3.Connection) -> list[str]:
    if "alembic_version" not in _sqlite_tables(connection):
        return []
    return sorted(
        str(row[0])
        for row in connection.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        ).fetchall()
    )


def _integrity(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "missing_result"


def _foreign_key_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    grouped = Counter((str(row[0]), str(row[2])) for row in rows)
    return {
        "violation_count": len(rows),
        "groups": [
            {"table": table, "parent_table": parent, "count": count}
            for (table, parent), count in sorted(grouped.items())
        ],
    }


def _canonical_value(value: Any) -> Any:
    if value is None:
        return ["null"]
    if isinstance(value, bytes):
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if isinstance(value, float):
        if math.isnan(value):
            return ["float", "nan"]
        if math.isinf(value):
            return ["float", "inf" if value > 0 else "-inf"]
        return ["float", value.hex()]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, str):
        return ["str", value]
    return [type(value).__name__, repr(value)]


def _table_fingerprint(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    available = [
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quote_identifier(table)})"
        ).fetchall()
    ]
    selected = list(columns) if columns is not None else available
    missing = sorted(set(selected) - set(available))
    if missing:
        raise ReconciliationError(
            f"candidate table {table!r} lost source columns: {missing}"
        )
    select_list = ", ".join(_quote_identifier(item) for item in selected)
    rows = connection.execute(
        f"SELECT {select_list} FROM {_quote_identifier(table)}"
    ).fetchall()
    canonical_rows = sorted(
        json.dumps(
            [_canonical_value(value) for value in row],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row in rows
    )
    digest = hashlib.sha256()
    for row in canonical_rows:
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return {
        "columns": selected,
        "row_count": len(rows),
        "digest_sha256": digest.hexdigest(),
    }


def _canonical_table_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> Counter[str]:
    select_list = ", ".join(_quote_identifier(item) for item in columns)
    rows = connection.execute(
        f"SELECT {select_list} FROM {_quote_identifier(table)}"
    ).fetchall()
    return Counter(
        json.dumps(
            [_canonical_value(value) for value in row],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for row in rows
    )


def _missing_organization_references(
    connection: sqlite3.Connection,
) -> dict[str, Counter[str]]:
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    by_organization: dict[str, Counter[str]] = defaultdict(Counter)
    constraints = sorted({(str(row[0]), str(row[2]), int(row[3])) for row in violations})
    for table, parent, foreign_key_index in constraints:
        if parent != "organizations":
            continue
        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({_quote_identifier(table)})"
        ).fetchall()
        match = next(
            (row for row in foreign_keys if int(row[0]) == foreign_key_index),
            None,
        )
        if match is None:
            raise ReconciliationError(
                f"could not resolve foreign key {foreign_key_index} on {table}"
            )
        child_column = str(match[3])
        query = (
            f"SELECT {_quote_identifier(child_column)}, COUNT(*) "
            f"FROM {_quote_identifier(table)} "
            f"WHERE {_quote_identifier(child_column)} IS NOT NULL "
            f"AND {_quote_identifier(child_column)} NOT IN "
            "(SELECT id FROM organizations) "
            f"GROUP BY {_quote_identifier(child_column)}"
        )
        for organization_id, count in connection.execute(query).fetchall():
            by_organization[str(organization_id)][table] += int(count)
    return dict(by_organization)


def _safe_missing_organization_summary(
    references: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    return [
        {
            "organization_id_sha256": hashlib.sha256(
                organization_id.encode("utf-8")
            ).hexdigest(),
            "empty_identifier": organization_id == "",
            "referencing_rows": sum(counts.values()),
            "tables": dict(sorted(counts.items())),
        }
        for organization_id, counts in sorted(references.items())
    ]


def _quarantine_missing_organizations(
    candidate: Path,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(candidate)
    try:
        foreign_key_summary = _foreign_key_summary(connection)
        unsupported = [
            item
            for item in foreign_key_summary["groups"]
            if item["parent_table"] != "organizations"
        ]
        if unsupported:
            raise ReconciliationError(
                "automatic quarantine only supports missing organization parents; "
                f"found {unsupported}"
            )
        references = _missing_organization_references(connection)
        repairs = _safe_missing_organization_summary(references)
        for organization_id, counts in sorted(references.items()):
            digest = hashlib.sha256(organization_id.encode("utf-8")).hexdigest()
            slug = f"recovered-{digest[:24]}"
            name = f"Quarantined recovered tenant {digest[:12]}"
            settings = json.dumps(
                {
                    "reconciliation_status": "quarantined_missing_parent",
                    "source_revision": "legacy",
                    "reference_count": sum(counts.values()),
                },
                separators=(",", ":"),
            )
            connection.execute(
                "INSERT INTO organizations "
                "(id, name, slug, plan, settings, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (organization_id, name, slug, "free", settings, 0),
            )
        connection.commit()
        remaining = _foreign_key_summary(connection)
        if remaining["violation_count"]:
            raise ReconciliationError(
                "quarantine repair did not clear all foreign-key violations: "
                f"{remaining['groups']}"
            )
        return repairs
    finally:
        connection.close()


def _database_fingerprints(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        table: _table_fingerprint(connection, table)
        for table in _sqlite_tables(connection)
        if table != "alembic_version"
    }


def inspect_database(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ReconciliationError(f"source database does not exist: {resolved}")
    if resolved.stat().st_size < 100:
        raise ReconciliationError(f"source database is empty or truncated: {resolved}")
    with resolved.open("rb") as handle:
        if handle.read(16) != b"SQLite format 3\x00":
            raise ReconciliationError(f"source is not a SQLite 3 database: {resolved}")
    with _connect_read_only(resolved) as connection:
        tables = _sqlite_tables(connection)
        foreign_keys = _foreign_key_summary(connection)
        missing_organizations = _safe_missing_organization_summary(
            _missing_organization_references(connection)
        )
        return {
            "path": str(resolved),
            "size_bytes": resolved.stat().st_size,
            "sha256": _sha256(resolved),
            "integrity_check": _integrity(connection),
            "foreign_key_violation_count": foreign_keys["violation_count"],
            "foreign_key_violation_groups": foreign_keys["groups"],
            "missing_organization_parent_count": len(missing_organizations),
            "missing_organization_parents": missing_organizations,
            "alembic_revisions": _alembic_revisions(connection),
            "table_count": len(tables),
            "data_table_count": len([item for item in tables if item != "alembic_version"]),
        }


def _current_head(backend_root: Path = BACKEND_ROOT) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "heads"],
        cwd=backend_root,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise ReconciliationError(
            f"could not resolve Alembic head: {result.stderr.strip()}"
        )
    heads = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    if len(heads) != 1:
        raise ReconciliationError(f"expected one Alembic head, found {heads}")
    return heads[0]


def _sqlite_backup(source: Path, candidate: Path) -> None:
    if candidate.exists():
        raise ReconciliationError(f"refusing to overwrite candidate: {candidate}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    source_connection = _connect_read_only(source)
    destination = sqlite3.connect(candidate)
    try:
        source_connection.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source_connection.close()


def _upgrade_candidate(candidate: Path, backend_root: Path = BACKEND_ROOT) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{candidate.resolve().as_posix()}",
            "ICODER_CREDENTIAL_LLM": "",
            "LLM_PROVIDER": "mock",
            "ICODER_ALLOW_EXTERNAL_LLM": "false",
            "ICODER_DISABLE_NATIVE_MEDCODER": "true",
            "ICODER_DATABASE_SQL_ECHO": "false",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        cwd=backend_root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    return {
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def _copy_source_tables(snapshot: Path, candidate: Path) -> dict[str, Any]:
    source = _connect_read_only(snapshot)
    destination = sqlite3.connect(candidate)
    try:
        source_tables = [
            table for table in _sqlite_tables(source) if table != "alembic_version"
        ]
        target_tables = set(_sqlite_tables(destination))
        source_only = sorted(set(source_tables) - target_tables)
        if source_only:
            raise ReconciliationError(
                f"head schema would discard source tables: {source_only}"
            )
        destination.execute("PRAGMA foreign_keys=OFF")
        ordered_tables = sorted(
            source_tables,
            key=lambda item: (item != "organizations", item),
        )
        copied: list[dict[str, Any]] = []
        for table in ordered_tables:
            source_columns = [
                str(row[1])
                for row in source.execute(
                    f"PRAGMA table_info({_quote_identifier(table)})"
                ).fetchall()
            ]
            target_columns = {
                str(row[1])
                for row in destination.execute(
                    f"PRAGMA table_info({_quote_identifier(table)})"
                ).fetchall()
            }
            missing_columns = sorted(set(source_columns) - target_columns)
            if missing_columns:
                raise ReconciliationError(
                    f"head schema would discard {table} columns: {missing_columns}"
                )
            target_count = int(
                destination.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table)}"
                ).fetchone()[0]
            )
            if target_count:
                raise ReconciliationError(
                    f"target table {table!r} is unexpectedly non-empty"
                )
            column_list = ", ".join(
                _quote_identifier(column) for column in source_columns
            )
            rows = source.execute(
                f"SELECT {column_list} FROM {_quote_identifier(table)}"
            ).fetchall()
            if rows:
                placeholders = ", ".join("?" for _ in source_columns)
                destination.executemany(
                    f"INSERT INTO {_quote_identifier(table)} ({column_list}) "
                    f"VALUES ({placeholders})",
                    rows,
                )
            copied.append({"table": table, "row_count": len(rows)})
        destination.commit()
        return {
            "table_count": len(copied),
            "row_count": sum(item["row_count"] for item in copied),
            "tables": copied,
        }
    finally:
        destination.close()
        source.close()


def stage_copy_upgrade(
    source: Path,
    output_dir: Path,
    *,
    backend_root: Path = BACKEND_ROOT,
    candidate_name: str = "icoder.reconciled-head.db",
    quarantine_orphan_organizations: bool = False,
) -> dict[str, Any]:
    source = source.resolve()
    output_dir = output_dir.resolve()
    candidate = output_dir / candidate_name
    snapshot = output_dir / "icoder.source-snapshot.db"
    for target in (snapshot, candidate):
        if target.exists():
            raise ReconciliationError(f"refusing to overwrite staged artifact: {target}")
    source_before = inspect_database(source)
    if source_before["integrity_check"] != "ok":
        raise ReconciliationError(
            f"source integrity_check failed: {source_before['integrity_check']}"
        )
    if (
        source_before["foreign_key_violation_count"]
        and not quarantine_orphan_organizations
    ):
        raise ReconciliationError(
            "source has foreign-key violations; pass "
            "--quarantine-orphan-organizations to repair only missing organization "
            "parents on the staged copy"
        )
    unsupported_foreign_keys = [
        item
        for item in source_before["foreign_key_violation_groups"]
        if item["parent_table"] != "organizations"
    ]
    if unsupported_foreign_keys:
        raise ReconciliationError(
            "source contains unsupported foreign-key violations: "
            f"{unsupported_foreign_keys}"
        )
    head = _current_head(backend_root)
    with _connect_read_only(source) as source_connection:
        source_fingerprints = _database_fingerprints(source_connection)

    _sqlite_backup(source, snapshot)
    snapshot_inspection = inspect_database(snapshot)
    migration = _upgrade_candidate(candidate, backend_root)
    if migration["returncode"] != 0:
        raise ReconciliationError(
            "candidate Alembic upgrade failed: " + migration["stderr_tail"]
        )
    copy_result = _copy_source_tables(snapshot, candidate)
    quarantine_repairs: list[dict[str, Any]] = []
    if source_before["foreign_key_violation_count"]:
        quarantine_repairs = _quarantine_missing_organizations(candidate)

    candidate_after = inspect_database(candidate)
    with _connect_read_only(candidate) as candidate_connection:
        candidate_fingerprints = {
            table: _table_fingerprint(
                candidate_connection,
                table,
                details["columns"],
            )
            for table, details in source_fingerprints.items()
        }
    mismatches: list[str] = []
    for table, source_details in source_fingerprints.items():
        candidate_details = candidate_fingerprints.get(table)
        if candidate_details == source_details:
            continue
        if table == "organizations" and quarantine_repairs:
            with _connect_read_only(source) as source_connection:
                source_rows = _canonical_table_rows(
                    source_connection, table, source_details["columns"]
                )
            with _connect_read_only(candidate) as candidate_connection:
                candidate_rows = _canonical_table_rows(
                    candidate_connection, table, source_details["columns"]
                )
            if all(candidate_rows[row] >= count for row, count in source_rows.items()):
                continue
        mismatches.append(table)

    from app.services.schema_drift_service import check_drift

    drift = check_drift(f"sqlite:///{candidate.as_posix()}").to_dict()
    source_after = inspect_database(source)
    source_unchanged = (
        source_before["sha256"] == source_after["sha256"]
        and source_before["size_bytes"] == source_after["size_bytes"]
        and source_before["alembic_revisions"] == source_after["alembic_revisions"]
    )
    checks = {
        "source_unchanged": source_unchanged,
        "candidate_integrity_ok": candidate_after["integrity_check"] == "ok",
        "candidate_foreign_keys_ok": candidate_after["foreign_key_violation_count"] == 0,
        "candidate_at_single_head": candidate_after["alembic_revisions"] == [head],
        "preexisting_data_preserved": not mismatches,
        "candidate_matches_orm": drift["summary"]["total"] == 0,
    }
    report = {
        "schema_version": "icoder.sqlite-migration-stage/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow_rebuild_head_source_read_only",
        "source": source_before,
        "source_after": source_after,
        "source_snapshot": snapshot_inspection,
        "source_snapshot_path": str(snapshot),
        "candidate": candidate_after,
        "candidate_path": str(candidate),
        "quarantine_orphan_organizations_requested": quarantine_orphan_organizations,
        "quarantine_repairs": quarantine_repairs,
        "alembic_head": head,
        "migration": migration,
        "copy_result": copy_result,
        "preexisting_table_fingerprints_before": source_fingerprints,
        "preexisting_table_fingerprints_after": candidate_fingerprints,
        "data_preservation_mismatches": mismatches,
        "schema_drift": drift,
        "checks": checks,
        "passed": all(checks.values()),
        "cutover_performed": False,
    }
    # The report contains only counts, schema identifiers, paths and digests.
    # It never includes source row values.
    report_path = output_dir / "sqlite_migration_stage_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report["report_path"] = str(report_path)
    if not report["passed"]:
        raise ReconciliationError(
            "staged migration verification failed: "
            + ", ".join(name for name, passed in checks.items() if not passed)
        )
    return report


def _inspection_report(source: Path) -> dict[str, Any]:
    return {
        "schema_version": "icoder.sqlite-migration-inspection/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "inspection_only_source_read_only",
        "source": inspect_database(source),
        "alembic_head": _current_head(),
        "source_modified": False,
        "candidate_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or stage an Alembic upgrade on a read-only SQLite source"
    )
    parser.add_argument("--source", type=Path, default=Path("data/icoder.db"))
    parser.add_argument("--stage-copy-upgrade", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--candidate-name", default="icoder.reconciled-head.db")
    parser.add_argument(
        "--quarantine-orphan-organizations",
        action="store_true",
        help=(
            "On the staged copy only, create inactive quarantine parent rows for "
            "missing organization IDs. Other FK violation types still fail."
        ),
    )
    args = parser.parse_args()
    try:
        if args.stage_copy_upgrade:
            if args.output_dir is None:
                raise ReconciliationError(
                    "--output-dir is required with --stage-copy-upgrade"
                )
            report = stage_copy_upgrade(
                args.source,
                args.output_dir,
                candidate_name=args.candidate_name,
                quarantine_orphan_organizations=args.quarantine_orphan_organizations,
            )
        else:
            report = _inspection_report(args.source)
    except ReconciliationError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "icoder.sqlite-migration-error/v1",
                    "error": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
