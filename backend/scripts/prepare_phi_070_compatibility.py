"""Restore populated revision-070 JSON/text semantics after schema rollback.

Run only after 072 values have been reverse-rotated to v1 and Alembic has been
downgraded to 070.  The operation intentionally restores plaintext for fields
that revision 070 applications cannot decrypt.  It therefore requires a fully
drained maintenance window and an explicit acknowledgement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.phi_encryption import decrypt_phi, is_encrypted_value  # noqa: E402
from scripts.backfill_phi_envelopes import JSON_COLUMNS, TEXT_COLUMNS, _url  # noqa: E402


PRESERVE_ENCRYPTED_TEXT = {
    "clinical_facts": {"encrypted_text", "encrypted_evidence_json"},
    "guided_documents": {
        "encrypted_string_document_json", "encrypted_structured_document_json",
        "encrypted_labels_json", "encrypted_classic_sections_json",
    },
    "guided_sections": {"encrypted_definition_json"},
}


def _legacy_text_columns() -> dict[str, tuple[str, ...]]:
    return {
        table: tuple(
            column for column in columns
            if column not in PRESERVE_ENCRYPTED_TEXT.get(table, set())
        )
        for table, columns in TEXT_COLUMNS.items()
        if any(column not in PRESERVE_ENCRYPTED_TEXT.get(table, set()) for column in columns)
    }


def run(database_url: str, *, execute: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    with psycopg.connect(_url(database_url)) as connection:
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            revision = str(cursor.fetchone()[0])
            if revision != "070":
                raise RuntimeError(f"070 compatibility restore requires revision 070; found {revision}")
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext('icoder.phi.rollback.070'))"
            )
            if not cursor.fetchone()[0]:
                raise RuntimeError("another PHI rollback operation is active")
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND state<>'idle'"
            )
            active_sessions = int(cursor.fetchone()[0])
            if active_sessions:
                raise RuntimeError(
                    f"database is not drained; {active_sessions} other active session(s) remain"
                )
            cursor.execute("SELECT id FROM organizations ORDER BY id")
            organizations = [str(row[0]) for row in cursor.fetchall()]

            for organization_id in organizations:
                cursor.execute(
                    "SELECT set_config('icoder.current_organization_id', %s, true)",
                    (organization_id,),
                )
                for is_json, mapping in ((False, _legacy_text_columns()), (True, JSON_COLUMNS)):
                    for table, columns in mapping.items():
                        identifiers = [sql.Identifier("id"), *(sql.Identifier(c) for c in columns)]
                        cursor.execute(
                            sql.SQL("SELECT {} FROM {} ORDER BY id").format(
                                sql.SQL(", ").join(identifiers), sql.Identifier(table),
                            )
                        )
                        for row in cursor.fetchall():
                            row_id = row[0]
                            for column, stored in zip(columns, row[1:]):
                                if stored is None or stored == "":
                                    continue
                                if not isinstance(stored, str) or not is_encrypted_value(stored):
                                    raise RuntimeError(
                                        f"unexpected rollback representation in {table}.{column}"
                                    )
                                plaintext = decrypt_phi(stored)
                                replacement = json.loads(plaintext) if is_json else plaintext
                                key = f"{table}.{column}"
                                counts[key] += 1
                                if execute:
                                    cursor.execute(
                                        sql.SQL("UPDATE {} SET {}=%s WHERE id=%s").format(
                                            sql.Identifier(table), sql.Identifier(column),
                                        ),
                                        (Jsonb(replacement) if is_json else replacement, row_id),
                                    )
                                    if cursor.rowcount != 1:
                                        raise RuntimeError(
                                            f"concurrent update detected in {table}.{column}"
                                        )
    manifest = {
        "schema_version": "icoder.phi-070-compatibility/v1",
        "mode": "execute" if execute else "dry_run",
        "organizations_scanned": len(organizations),
        "values": sum(counts.values()),
        "columns": {key: value for key, value in sorted(counts.items()) if value},
        "plaintext_at_rest": bool(execute and counts),
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--maintenance-confirm", default="")
    parser.add_argument("--acknowledge-plaintext-at-rest", action="store_true")
    args = parser.parse_args()
    if args.execute and (
        args.maintenance_confirm != "RESTORE_070_SEMANTICS"
        or not args.acknowledge_plaintext_at_rest
    ):
        raise RuntimeError(
            "execute requires --maintenance-confirm RESTORE_070_SEMANTICS "
            "and --acknowledge-plaintext-at-rest"
        )
    database_url = os.environ.get("P1_POSTGRES_MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("P1_POSTGRES_MIGRATION_DATABASE_URL is required")
    print(json.dumps(run(database_url, execute=args.execute), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
