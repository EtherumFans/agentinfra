"""Resumable online PHI envelope rotation for revisions 072 through 074.

The forward v1->v2 path is safe while the dual-reader/v2-writer application is
serving traffic.  Rows are locked in small batches and committed independently;
rerunning skips completed v2 values.  Reverse rotation is a maintenance-only
rollback prerequisite.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

import psycopg
from psycopg import sql


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.phi_encryption import (  # noqa: E402
    decrypt_phi,
    encrypt_phi,
    encrypt_phi_v1,
    is_encrypted_value,
)
from scripts.backfill_phi_envelopes import JSON_COLUMNS, TEXT_COLUMNS, _url  # noqa: E402


def _all_columns() -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = defaultdict(list)
    for mapping in (TEXT_COLUMNS, JSON_COLUMNS):
        for table, columns in mapping.items():
            merged[table].extend(columns)
    return {table: tuple(columns) for table, columns in merged.items()}


def _source_clause(target: str, identifier: sql.Identifier) -> sql.Composed:
    if target == "v2":
        return sql.SQL("{} LIKE 'v1:gAAAAA%%'").format(identifier)
    return sql.SQL("{} LIKE 'v2:%%' AND {} NOT LIKE 'v2:gAAAAA%%'").format(
        identifier, identifier
    )


def _target_encryptor(target: str) -> Callable[[str], str | None]:
    return encrypt_phi if target == "v2" else encrypt_phi_v1


def run(database_url: str, *, target: str, execute: bool, batch_size: int) -> dict:
    if target not in {"v1", "v2"}:
        raise ValueError("target must be v1 or v2")
    counts: dict[str, int] = defaultdict(int)
    encryptor = _target_encryptor(target)
    with psycopg.connect(_url(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            revision = str(cursor.fetchone()[0])
            if revision not in {"072", "073", "074"}:
                raise RuntimeError(
                    f"PHI rotation requires compatible revision 072, 073, or 074; found {revision}"
                )
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtext('icoder.phi.rotation.v2'))"
            )
            if not cursor.fetchone()[0]:
                raise RuntimeError("another PHI rotation process already holds the lock")
            cursor.execute("SELECT id FROM organizations ORDER BY id")
            organizations = [str(row[0]) for row in cursor.fetchall()]
        connection.commit()

        for organization_id in organizations:
            for table, columns in _all_columns().items():
                for column in columns:
                    key = f"{table}.{column}"
                    if not execute:
                        with connection.transaction(), connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT set_config('icoder.current_organization_id', %s, true)",
                                (organization_id,),
                            )
                            clause = _source_clause(target, sql.Identifier(column))
                            cursor.execute(
                                sql.SQL("SELECT count(*) FROM {} WHERE ").format(
                                    sql.Identifier(table)
                                ) + clause
                            )
                            counts[key] += int(cursor.fetchone()[0])
                        continue

                    while True:
                        with connection.transaction(), connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT set_config('icoder.current_organization_id', %s, true)",
                                (organization_id,),
                            )
                            identifier = sql.Identifier(column)
                            clause = _source_clause(target, identifier)
                            cursor.execute(
                                sql.SQL("SELECT id, {} FROM {} WHERE ").format(
                                    identifier, sql.Identifier(table)
                                ) + clause + sql.SQL(
                                    " ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
                                ),
                                (batch_size,),
                            )
                            rows = cursor.fetchall()
                            if not rows:
                                break
                            for row_id, stored in rows:
                                if not isinstance(stored, str) or not is_encrypted_value(stored):
                                    raise RuntimeError(
                                        f"malformed encrypted value in {key}; rotation stopped"
                                    )
                                plaintext = decrypt_phi(stored)
                                rotated = encryptor(plaintext)
                                if not rotated or not is_encrypted_value(rotated):
                                    raise RuntimeError(f"rotation did not produce an envelope for {key}")
                                cursor.execute(
                                    sql.SQL("UPDATE {} SET {}=%s WHERE id=%s AND {}=%s").format(
                                        sql.Identifier(table), identifier, identifier,
                                    ),
                                    (rotated, row_id, stored),
                                )
                                if cursor.rowcount != 1:
                                    raise RuntimeError(f"concurrent PHI update detected in {key}")
                                counts[key] += 1

    return {
        "schema_version": "icoder.phi-rotation/v2",
        "mode": "execute" if execute else "dry_run",
        "target": target,
        "batch_size": batch_size,
        "organizations_scanned": len(organizations),
        "values": sum(counts.values()),
        "columns": {key: value for key, value in sorted(counts.items()) if value},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("v1", "v2"), default="v2")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--maintenance-confirm", default="")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000:
        raise RuntimeError("batch size must be between 1 and 5000")
    if args.target == "v1" and args.execute and args.maintenance_confirm != "REVERSE_TO_V1":
        raise RuntimeError(
            "reverse rotation requires --maintenance-confirm REVERSE_TO_V1"
        )
    database_url = os.environ.get("P1_POSTGRES_MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("P1_POSTGRES_MIGRATION_DATABASE_URL is required")
    print(json.dumps(run(
        database_url, target=args.target, execute=args.execute,
        batch_size=args.batch_size,
    ), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
