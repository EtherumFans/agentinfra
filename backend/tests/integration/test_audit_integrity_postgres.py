"""Live PostgreSQL gate for revision 070's immutable audit archive."""

from __future__ import annotations

import json
import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError


APP_URL = os.getenv("P1_POSTGRES_TEST_DATABASE_URL", "")
MIGRATION_URL = os.getenv("P1_POSTGRES_MIGRATION_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not (APP_URL.startswith("postgresql") and MIGRATION_URL.startswith("postgresql")),
    reason="P1 PostgreSQL application and migration URLs are not configured",
)


def _sync(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def _tenant(connection: sa.Connection, organization_id: str) -> None:
    connection.execute(sa.text(
        "SELECT set_config('icoder.current_organization_id', :org, true)"
    ), {"org": organization_id})


def _archive_record(audit_id: str, organization_id: str | None, *, sequence: int = 1,
                    previous_hash: str = "0" * 64) -> str:
    return json.dumps({
        "id": uuid.uuid4().hex[:12],
        "audit_log_id": audit_id,
        "organization_id": organization_id,
        "stream_id": organization_id or "system",
        "sequence": sequence,
        "payload": {"audit_log_id": audit_id, "schema": "icoder.audit-archive.v1"},
        "payload_hash": "1" * 64,
        "previous_hash": previous_hash,
        "chain_hash": "2" * 64,
        "signature": "test-signature",
        "signing_algorithm": "HMAC-SHA256",
        "signing_key_id": "integration-v1",
        "archived_at": "2026-09-01T00:00:00+00:00",
    })


def test_tenant_and_system_append_are_isolated_and_immutable() -> None:
    app = sa.create_engine(_sync(APP_URL))
    migration = sa.create_engine(_sync(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"a70a{suffix}", f"a70b{suffix}"
    tenant_audit, system_audit = f"ta{suffix}", f"sa{suffix}"
    try:
        with migration.begin() as connection:
            for org in (org_a, org_b):
                connection.execute(sa.text(
                    "INSERT INTO organizations (id,name,slug,plan,settings,is_active) "
                    "VALUES (:id,:id,:id,'free',CAST('{}' AS json),true)"
                ), {"id": org})

        with app.begin() as connection:
            _tenant(connection, org_a)
            connection.execute(sa.text(
                "INSERT INTO audit_logs (id,organization_id,action,resource_type,status,"
                "tenancy_classification) VALUES (:id,:org,'archive.test','test',"
                "'success','MODERN')"
            ), {"id": tenant_audit, "org": org_a})
            connection.execute(sa.text(
                "SELECT icoder_append_audit_archive(CAST(:record AS jsonb))"
            ), {"record": _archive_record(tenant_audit, org_a)})

        with app.begin() as connection:
            connection.execute(sa.text(
                "SELECT icoder_write_system_audit(CAST(:event AS jsonb))"
            ), {"event": json.dumps({
                "id": system_audit, "action": "system.startup",
                "resource_type": "system", "details": {"gate": "070"},
            })})
            system_head = connection.execute(sa.text(
                "SELECT sequence, chain_hash FROM icoder_audit_archive_head(NULL)"
            )).one()
            connection.execute(sa.text(
                "SELECT icoder_append_audit_archive(CAST(:record AS jsonb))"
            ), {"record": _archive_record(
                system_audit, None, sequence=int(system_head.sequence) + 1,
                previous_hash=str(system_head.chain_hash),
            )})

        with app.begin() as connection:
            _tenant(connection, org_a)
            assert connection.execute(sa.text(
                "SELECT audit_log_id FROM audit_integrity_archive"
            )).scalars().all() == [tenant_audit]
            result = connection.execute(sa.text(
                "UPDATE audit_integrity_archive SET signature='tampered' "
                "WHERE audit_log_id=:id"
            ), {"id": tenant_audit})
            assert result.rowcount == 0

        with app.begin() as connection:
            _tenant(connection, org_b)
            assert connection.execute(sa.text(
                "SELECT count(*) FROM audit_integrity_archive"
            )).scalar_one() == 0

        # The owner is allowed through FORCE RLS, so the trigger—not an empty
        # RLS result—must reject both physical mutation operations.
        for statement in (
            "UPDATE audit_integrity_archive SET signature='tampered' WHERE audit_log_id=:id",
            "DELETE FROM audit_integrity_archive WHERE audit_log_id=:id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                with migration.begin() as connection:
                    connection.execute(sa.text(statement), {"id": tenant_audit})

        # A stale/broken predecessor is rejected under the per-stream lock.
        second_audit = f"tb{suffix}"
        with pytest.raises(DBAPIError, match="chain head changed"):
            with app.begin() as connection:
                _tenant(connection, org_a)
                connection.execute(sa.text(
                    "INSERT INTO audit_logs (id,organization_id,action,resource_type,status,"
                    "tenancy_classification) VALUES (:id,:org,'archive.test.2','test',"
                    "'success','MODERN')"
                ), {"id": second_audit, "org": org_a})
                connection.execute(sa.text(
                    "SELECT icoder_append_audit_archive(CAST(:record AS jsonb))"
                ), {"record": _archive_record(second_audit, org_a, sequence=2,
                                               previous_hash="f" * 64)})
    finally:
        app.dispose()
        migration.dispose()
