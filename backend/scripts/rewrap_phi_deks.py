"""Online KEK rotation by rewrapping PHI data keys at revision 072.

The command is dry-run by default.  It never decrypts PHI ciphertext: the old
KEK unwraps only the 32-byte DEK and the active KEK immediately rewraps it.
Small tenant-scoped batches, optimistic updates, and keyset pagination make a
run restartable while application traffic continues.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.phi_encryption import phi_v2_key_id, rewrap_phi_v2  # noqa: E402
from app.services.soft_hsm import SoftwareHSMKeyring  # noqa: E402
from app.services.system_audit import system_audit  # noqa: E402
from scripts.backfill_phi_envelopes import JSON_COLUMNS, TEXT_COLUMNS, _url  # noqa: E402


def _all_columns() -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = defaultdict(list)
    for mapping in (TEXT_COLUMNS, JSON_COLUMNS):
        for table, columns in mapping.items():
            merged[table].extend(columns)
    return {table: tuple(columns) for table, columns in merged.items()}


def run(database_url: str, *, execute: bool, batch_size: int) -> dict:
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch size must be between 1 and 5000")
    keyring = SoftwareHSMKeyring.from_environment()
    references: Counter[str] = Counter()
    changed: Counter[str] = Counter()
    columns_changed: Counter[str] = Counter()
    scanned = 0

    with psycopg.connect(_url(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            revision = str(cursor.fetchone()[0])
            if revision != "072":
                raise RuntimeError(f"PHI DEK rewrap requires revision 072; found {revision}")
            cursor.execute("SELECT pg_try_advisory_lock(hashtext('icoder.phi.dek-rewrap.v2'))")
            if not cursor.fetchone()[0]:
                raise RuntimeError("another PHI DEK rewrap process already holds the lock")
            cursor.execute("SELECT id FROM organizations ORDER BY id")
            organizations = [str(row[0]) for row in cursor.fetchall()]
        connection.commit()

        for organization_id in organizations:
            for table, columns in _all_columns().items():
                for column in columns:
                    last_pk: str | None = None
                    while True:
                        with connection.transaction(), connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT set_config('icoder.current_organization_id', %s, true)",
                                (organization_id,),
                            )
                            identifier = sql.Identifier(column)
                            predicate = sql.SQL(
                                "{} LIKE 'v2:%%' AND {} NOT LIKE 'v2:gAAAAA%%'"
                            ).format(identifier, identifier)
                            parameters: list[object] = []
                            if last_pk is not None:
                                predicate += sql.SQL(" AND id > %s")
                                parameters.append(last_pk)
                            parameters.append(batch_size)
                            cursor.execute(
                                sql.SQL("SELECT id, {} FROM {} WHERE ").format(
                                    identifier, sql.Identifier(table)
                                ) + predicate + sql.SQL(
                                    " ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
                                ),
                                parameters,
                            )
                            rows = cursor.fetchall()
                            if not rows:
                                break
                            for row_id, stored in rows:
                                last_pk = str(row_id)
                                if not isinstance(stored, str):
                                    raise RuntimeError(
                                        f"non-text PHI envelope in {table}.{column}"
                                    )
                                old_key_id = phi_v2_key_id(stored)
                                references[old_key_id] += 1
                                scanned += 1
                                if old_key_id == keyring.active_key_id:
                                    continue
                                # Resolve before counting dry-run changes so a missing,
                                # retired, or revoked old key fails the gate immediately.
                                keyring.resolve(old_key_id, operation="unwrap")
                                changed[old_key_id] += 1
                                columns_changed[f"{table}.{column}"] += 1
                                if not execute:
                                    continue
                                rewrapped = rewrap_phi_v2(stored)
                                cursor.execute(
                                    sql.SQL("UPDATE {} SET {}=%s WHERE id=%s AND {}=%s").format(
                                        sql.Identifier(table), identifier, identifier,
                                    ),
                                    (rewrapped, row_id, stored),
                                )
                                if cursor.rowcount != 1:
                                    raise RuntimeError(
                                        f"concurrent PHI update detected in {table}.{column}"
                                    )

    return {
        "schema_version": "icoder.phi-dek-rewrap/v1",
        "mode": "execute" if execute else "dry_run",
        "active_key_id": keyring.active_key_id,
        "keyring_generation": keyring.generation,
        "keyring_source": keyring.source,
        "key_states": keyring.public_statuses(),
        "organizations_scanned": len(organizations),
        "values_scanned": scanned,
        "values_to_rewrap": sum(changed.values()),
        "references_by_key_before": dict(sorted(references.items())),
        "rewrapped_from_key": dict(sorted(changed.items())),
        "columns": dict(sorted(columns_changed.items())),
        "retirement_ready": not changed,
    }


def _async_url(value: str) -> str:
    value = _url(value)
    return value.replace("postgresql://", "postgresql+asyncpg://", 1)


async def _emit_audit(
    database_url: str, *, action: str, key_id: str, details: dict, status: str = "success",
) -> None:
    """Commit a key lifecycle event and its signed immutable archive record."""
    engine = create_async_engine(_async_url(database_url), hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await system_audit(
                session,
                action=action,
                resource_type="phi_kek",
                resource_id=key_id,
                details=details,
                status=status,
            )
            await session.commit()
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()
    database_url = os.environ.get("P1_POSTGRES_MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("P1_POSTGRES_MIGRATION_DATABASE_URL is required")
    keyring = SoftwareHSMKeyring.from_environment()
    audit_url = os.environ.get("P1_POSTGRES_APP_DATABASE_URL", "").strip()
    if args.execute and not audit_url:
        raise RuntimeError(
            "P1_POSTGRES_APP_DATABASE_URL is required to seal key lifecycle audit events"
        )
    if args.execute:
        asyncio.run(_emit_audit(
            audit_url,
            action="phi.key_rewrap.started",
            key_id=keyring.active_key_id,
            details={
                "batch_size": args.batch_size,
                "provider": "software_hsm",
                "keyring_generation": keyring.generation,
                "keyring_source": keyring.source,
            },
        ))
    try:
        report = run(database_url, execute=args.execute, batch_size=args.batch_size)
        if args.execute:
            verification = run(database_url, execute=False, batch_size=args.batch_size)
            if verification["values_to_rewrap"]:
                raise RuntimeError("post-rewrap verification found old KEK references")
            report["post_verification"] = {
                "references_by_key": verification["references_by_key_before"],
                "retirement_ready": True,
            }
            report["retirement_ready"] = True
            asyncio.run(_emit_audit(
                audit_url,
                action="phi.key_rewrap.completed",
                key_id=keyring.active_key_id,
                details={
                    "values_rewrapped": report["values_to_rewrap"],
                    "organizations_scanned": report["organizations_scanned"],
                    "keyring_generation": report["keyring_generation"],
                    "keyring_source": report["keyring_source"],
                },
            ))
            asyncio.run(_emit_audit(
                audit_url,
                action="phi.key_retirement.verified",
                key_id=keyring.active_key_id,
                details={"old_key_references": 0},
            ))
    except Exception:
        if args.execute:
            asyncio.run(_emit_audit(
                audit_url,
                action="phi.key_rewrap.failed",
                key_id=keyring.active_key_id,
                details={"batch_size": args.batch_size},
                status="failure",
            ))
        raise
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
