from __future__ import annotations

import os
import secrets

import psycopg
import pytest
from psycopg import sql

from scripts.provision_postgresql_roles import (
    RoleSpec,
    normalize_postgresql_url,
    provision,
    verify,
)


ADMIN_URL = os.getenv("P1_POSTGRES_ADMIN_DATABASE_URL", "")


@pytest.mark.skipif(not ADMIN_URL, reason="requires P1_POSTGRES_ADMIN_DATABASE_URL")
def test_provisioning_is_idempotent_and_defaults_cover_new_objects() -> None:
    suffix = secrets.token_hex(5)
    schema_name = f"rbac_{suffix}"
    migration_role = f"rbac_migration_{suffix}"
    app_role = f"rbac_app_{suffix}"
    spec = RoleSpec(
        migration_role=migration_role,
        app_role=app_role,
        schema=schema_name,
    )
    connection = psycopg.connect(normalize_postgresql_url(ADMIN_URL), autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
            # Exercise adoption of an already migrated schema, not just
            # provisioning an empty one. Linked sequences must move with
            # their table while standalone sequences move independently.
            cursor.execute(sql.SQL(
                "CREATE TABLE {}.existing_serial (id bigserial PRIMARY KEY, value text)"
            ).format(sql.Identifier(schema_name)))
            cursor.execute(sql.SQL(
                "CREATE TABLE {}.existing_identity "
                "(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, value text)"
            ).format(sql.Identifier(schema_name)))
            cursor.execute(sql.SQL(
                "CREATE SEQUENCE {}.existing_standalone"
            ).format(sql.Identifier(schema_name)))
            for table in ("existing_serial", "existing_identity"):
                cursor.execute(sql.SQL(
                    "INSERT INTO {}.{} (value) VALUES ('before-provision') RETURNING id"
                ).format(sql.Identifier(schema_name), sql.Identifier(table)))
                assert cursor.fetchone()[0] == 1

        provision(connection, spec)
        provision(connection, spec)

        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(migration_role)))
            cursor.execute(
                sql.SQL("CREATE TABLE {}.records (id bigint GENERATED ALWAYS AS IDENTITY, value text)").format(
                    sql.Identifier(schema_name)
                )
            )
            cursor.execute(
                sql.SQL("CREATE FUNCTION {}.ping() RETURNS integer LANGUAGE sql AS 'SELECT 1'").format(
                    sql.Identifier(schema_name)
                )
            )
            cursor.execute("RESET ROLE")

        report = verify(connection, spec)
        assert report["ok"] is True, report
        assert report["objects_checked"] >= 7
        assert report["functions_checked"] == 1

        # Repeat after new IDENTITY objects exist; default privileges and
        # ownership reconciliation must both remain idempotent.
        provision(connection, spec)
        assert verify(connection, spec)["ok"] is True

        with connection.cursor() as cursor:
            for table in ("existing_serial", "existing_identity"):
                cursor.execute(sql.SQL(
                    "INSERT INTO {}.{} (value) VALUES ('after-provision') RETURNING id"
                ).format(sql.Identifier(schema_name), sql.Identifier(table)))
                assert cursor.fetchone()[0] == 2
                cursor.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
                    sql.Identifier(schema_name), sql.Identifier(table),
                ))
                assert cursor.fetchone()[0] == 2
            cursor.execute(
                "SELECT count(*) FROM pg_depend d "
                "JOIN pg_class c ON c.oid=d.objid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind='S' "
                "AND d.classid='pg_class'::regclass "
                "AND d.refclassid='pg_class'::regclass "
                "AND d.refobjsubid>0 AND d.deptype IN ('a', 'i')",
                (schema_name,),
            )
            assert cursor.fetchone()[0] == 3, "retain SERIAL/IDENTITY ownership links"
            cursor.execute(
                "SELECT rolinherit FROM pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
                ([migration_role, app_role],),
            )
            assert all(row[0] is False for row in cursor.fetchall())
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
            )
            for role in (app_role, migration_role):
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=%s)", (role,))
                if cursor.fetchone()[0]:
                    if role == migration_role:
                        cursor.execute(
                            sql.SQL("GRANT {} TO CURRENT_USER WITH SET TRUE").format(
                                sql.Identifier(role)
                            )
                        )
                        cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                    cursor.execute(
                        sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                            sql.Identifier(connection.info.dbname), sql.Identifier(role)
                        )
                    )
                    cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        connection.close()
