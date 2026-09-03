"""Provision and verify least-privilege PostgreSQL deployment roles.

The provisioning connection must be an existing role with CREATEROLE and
ownership of the target database objects (a managed-database administrator is
the usual choice).  Runtime and migration role names are inputs, never product
constants, so each deployment can follow its own identity convention.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


SAFE_ROLE_ATTRIBUTES = (
    "NOSUPERUSER",
    "NOBYPASSRLS",
    "NOCREATEDB",
    "NOCREATEROLE",
    "NOREPLICATION",
    "NOINHERIT",
    "LOGIN",
)
MANAGED_ADMIN_ROLE_ATTRIBUTES = (
    "NOINHERIT",
    "LOGIN",
)


def normalize_postgresql_url(value: str) -> str:
    """Convert SQLAlchemy PostgreSQL URLs to a libpq-compatible URL."""
    for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
        value = value.replace(driver, "", 1)
    if not value.startswith(("postgresql://", "postgres://")):
        raise ValueError("admin URL must use PostgreSQL")
    return value


@dataclass(frozen=True)
class RoleSpec:
    migration_role: str
    app_role: str
    schema: str
    migration_password: str | None = None
    app_password: str | None = None

    def validate(self) -> None:
        if not self.migration_role or not self.app_role or not self.schema:
            raise ValueError("migration role, app role, and schema are required")
        if self.migration_role == self.app_role:
            raise ValueError("migration and application roles must be distinct")


def _role_exists(cursor: Any, role: str) -> bool:
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (role,))
    return bool(cursor.fetchone()[0])


def _ensure_role(
    cursor: Any,
    role: str,
    password: str | None,
    *,
    provisioning_is_superuser: bool,
) -> None:
    identifier = sql.Identifier(role)
    if not _role_exists(cursor, role):
        cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(identifier))
    if provisioning_is_superuser:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH " + " ".join(SAFE_ROLE_ATTRIBUTES)).format(
                identifier
            )
        )
    else:
        # PostgreSQL reserves changes to SUPERUSER, BYPASSRLS, and REPLICATION
        # for superusers. Managed-service CREATEROLE administrators can create
        # safe roles, but must fail closed rather than pretending to repair an
        # already privileged identity.
        cursor.execute(
            "SELECT rolsuper, rolbypassrls, rolreplication, rolcreatedb, rolcreaterole "
            "FROM pg_roles WHERE rolname=%s",
            (role,),
        )
        state = cursor.fetchone()
        if state is None or any(state):
            raise PermissionError(
                f"role {role!r} has privileged attributes that require DBA repair"
            )
        cursor.execute(
            sql.SQL(
                "ALTER ROLE {} WITH " + " ".join(MANAGED_ADMIN_ROLE_ATTRIBUTES)
            ).format(identifier)
        )
    if password is not None:
        # PostgreSQL utility statements do not accept bind parameters here.
        # psycopg's Literal still performs server-compatible quoting without
        # interpolating the password into an untrusted SQL string.
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                identifier,
                sql.Literal(password),
            )
        )


def _transfer_object_ownership(cursor: Any, spec: RoleSpec) -> None:
    migration = sql.Identifier(spec.migration_role)
    cursor.execute(
        """
        SELECT c.relkind, c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
          AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
        ORDER BY c.relkind, c.relname
        """,
        (spec.schema,),
    )
    object_kinds = {
        "r": "TABLE",
        "p": "TABLE",
        "S": "SEQUENCE",
        "v": "VIEW",
        "m": "MATERIALIZED VIEW",
        "f": "FOREIGN TABLE",
    }
    for relkind, name in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER {} {}.{} OWNER TO {}").format(
                sql.SQL(object_kinds[relkind]),
                sql.Identifier(spec.schema),
                sql.Identifier(name),
                migration,
            )
        )

    cursor.execute(
        """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid)
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = %s
        ORDER BY p.proname, pg_get_function_identity_arguments(p.oid)
        """,
        (spec.schema,),
    )
    for name, arguments in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER FUNCTION {}.{}({}) OWNER TO {}").format(
                sql.Identifier(spec.schema),
                sql.Identifier(name),
                sql.SQL(arguments),
                migration,
            )
        )


def provision(connection: psycopg.Connection[Any], spec: RoleSpec) -> None:
    """Idempotently establish deployment roles and their object privileges."""
    spec.validate()
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"icoder-role-provisioning:{connection.info.dbname}:{spec.schema}",),
            )
            cursor.execute(
                "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname=current_user"
            )
            authority = cursor.fetchone()
            if authority is None or not (authority[0] or authority[1]):
                raise PermissionError("provisioning identity requires CREATEROLE")

            _ensure_role(
                cursor,
                spec.migration_role,
                spec.migration_password,
                provisioning_is_superuser=bool(authority[0]),
            )
            _ensure_role(
                cursor,
                spec.app_role,
                spec.app_password,
                provisioning_is_superuser=bool(authority[0]),
            )

            database = sql.Identifier(connection.info.dbname)
            schema = sql.Identifier(spec.schema)
            migration = sql.Identifier(spec.migration_role)
            app = sql.Identifier(spec.app_role)

            # PostgreSQL 16+ separates role administration from permission to
            # SET ROLE. Object ownership can only be transferred to a role the
            # provisioning identity may assume, so retain explicit SET
            # membership for future idempotent repairs and upgrades.
            cursor.execute(
                sql.SQL("GRANT {} TO CURRENT_USER WITH SET TRUE").format(migration)
            )
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                database, migration, app
            ))
            cursor.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(schema))
            cursor.execute(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(schema, migration))
            _transfer_object_ownership(cursor, spec)

            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, app))
            cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(schema, app))
            cursor.execute(
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC").format(
                    schema
                )
            )
            cursor.execute(
                sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM PUBLIC").format(
                    schema
                )
            )
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}"
                ).format(schema, app)
            )
            cursor.execute(
                sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
                    schema, app
                )
            )
            cursor.execute(
                sql.SQL("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC").format(
                    schema
                )
            )
            cursor.execute(
                sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {} TO {}").format(
                    schema, app
                )
            )

            # New Alembic-owned objects inherit the same runtime boundary.
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "REVOKE ALL ON TABLES FROM PUBLIC"
                ).format(migration, schema)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(migration, schema, app)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "REVOKE ALL ON SEQUENCES FROM PUBLIC"
                ).format(migration, schema)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(migration, schema, app)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} "
                    "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
                ).format(migration)
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                    "GRANT EXECUTE ON FUNCTIONS TO {}"
                ).format(migration, schema, app)
            )


def verify(connection: psycopg.Connection[Any], spec: RoleSpec) -> dict[str, Any]:
    """Return a stable verification report; ``ok`` is false on any drift."""
    spec.validate()
    failures: list[str] = []
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
                   rolreplication, rolinherit, rolcanlogin
            FROM pg_roles WHERE rolname = ANY(%s)
            """,
            ([spec.migration_role, spec.app_role],),
        )
        roles = {row["rolname"]: row for row in cursor.fetchall()}
        for name in (spec.migration_role, spec.app_role):
            state = roles.get(name)
            if state is None:
                failures.append(f"role_missing:{name}")
                continue
            for forbidden in (
                "rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole",
                "rolreplication", "rolinherit",
            ):
                if state[forbidden]:
                    failures.append(f"role_unsafe:{name}:{forbidden}")
            if not state["rolcanlogin"]:
                failures.append(f"role_cannot_login:{name}")

        # NOINHERIT is insufficient by itself: a runtime identity that is a
        # member of another role can still explicitly SET ROLE. Runtime has no
        # legitimate parent role, so any membership is release-blocking drift.
        cursor.execute(
            """
            SELECT parent.rolname
            FROM pg_auth_members membership
            JOIN pg_roles child ON child.oid=membership.member
            JOIN pg_roles parent ON parent.oid=membership.roleid
            WHERE child.rolname=%s
            ORDER BY parent.rolname
            """,
            (spec.app_role,),
        )
        for row in cursor.fetchall():
            failures.append(f"app_role_membership_present:{row['rolname']}")

        cursor.execute(
            """
            SELECT n.nspname, owner.rolname AS owner,
                   has_schema_privilege(%s, n.oid, 'USAGE') AS app_usage,
                   has_schema_privilege(%s, n.oid, 'CREATE') AS app_create,
                   EXISTS (
                     SELECT 1
                     FROM aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) acl
                     WHERE acl.grantee=0
                   ) AS public_privileges
            FROM pg_namespace n JOIN pg_roles owner ON owner.oid=n.nspowner
            WHERE n.nspname=%s
            """,
            (spec.app_role, spec.app_role, spec.schema),
        )
        schema_state = cursor.fetchone()
        if schema_state is None:
            failures.append(f"schema_missing:{spec.schema}")
        else:
            if schema_state["owner"] != spec.migration_role:
                failures.append("schema_owner_mismatch")
            if not schema_state["app_usage"] or schema_state["app_create"]:
                failures.append("schema_app_privileges_invalid")
            if schema_state["public_privileges"]:
                failures.append("schema_public_privileges_present")

        cursor.execute(
            """
            SELECT c.relkind, c.relname, owner.rolname AS owner,
                   CASE WHEN c.relkind = 'S' THEN
                     has_sequence_privilege(%s, c.oid, 'USAGE')
                     AND has_sequence_privilege(%s, c.oid, 'SELECT')
                   ELSE
                     has_table_privilege(%s, c.oid, 'SELECT')
                     AND has_table_privilege(%s, c.oid, 'INSERT')
                     AND has_table_privilege(%s, c.oid, 'UPDATE')
                     AND has_table_privilege(%s, c.oid, 'DELETE')
                   END AS app_privileges,
                   EXISTS (
                     SELECT 1 FROM aclexplode(coalesce(
                       c.relacl,
                       acldefault(CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END, c.relowner)
                     )) acl WHERE acl.grantee=0
                   ) AS public_privileges
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_roles owner ON owner.oid=c.relowner
            WHERE n.nspname=%s AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
            """,
            (
                spec.app_role, spec.app_role,
                spec.app_role, spec.app_role, spec.app_role, spec.app_role,
                spec.schema,
            ),
        )
        objects = cursor.fetchall()
        for item in objects:
            if item["owner"] != spec.migration_role:
                failures.append(f"object_owner_mismatch:{item['relname']}")
            if not item["app_privileges"]:
                failures.append(f"object_app_privileges_missing:{item['relname']}")
            if item["public_privileges"]:
                failures.append(f"object_public_privileges_present:{item['relname']}")

        cursor.execute(
            """
            SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS arguments,
                   owner.rolname AS owner,
                   has_function_privilege(%s, p.oid, 'EXECUTE') AS app_execute,
                   EXISTS (
                     SELECT 1
                     FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl
                     WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'
                   ) AS public_execute
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_roles owner ON owner.oid=p.proowner
            WHERE n.nspname=%s
            """,
            (spec.app_role, spec.schema),
        )
        functions = cursor.fetchall()
        for item in functions:
            signature = f"{item['proname']}({item['arguments']})"
            if item["owner"] != spec.migration_role:
                failures.append(f"function_owner_mismatch:{signature}")
            if not item["app_execute"]:
                failures.append(f"function_app_execute_missing:{signature}")
            if item["public_execute"]:
                failures.append(f"function_public_execute_present:{signature}")

        cursor.execute(
            """
            SELECT d.defaclobjtype, acl.grantee, acl.privilege_type
            FROM pg_default_acl d
            JOIN pg_roles owner ON owner.oid=d.defaclrole
            LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
            CROSS JOIN LATERAL aclexplode(d.defaclacl) acl
            WHERE owner.rolname=%s
              AND (d.defaclnamespace=0 OR n.nspname=%s)
            """,
            (spec.migration_role, spec.schema),
        )
        default_acl_rows = cursor.fetchall()
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (spec.app_role,))
        app_oid_row = cursor.fetchone()
        app_oid = app_oid_row["oid"] if app_oid_row else None
        default_acl: dict[str, set[str]] = {}
        public_default_acl: dict[str, set[str]] = {}
        for row in default_acl_rows:
            target = public_default_acl if row["grantee"] == 0 else default_acl
            if row["grantee"] in (0, app_oid):
                target.setdefault(row["defaclobjtype"], set()).add(row["privilege_type"])
        required_default_acl = {
            "r": {"SELECT", "INSERT", "UPDATE", "DELETE"},
            "S": {"SELECT", "USAGE"},
            "f": {"EXECUTE"},
        }
        for object_type, required in required_default_acl.items():
            if not required.issubset(default_acl.get(object_type, set())):
                failures.append(f"default_privileges_missing:{object_type}")
        if "EXECUTE" in public_default_acl.get("f", set()):
            failures.append("default_function_public_execute_present")
        for object_type in ("r", "S"):
            if public_default_acl.get(object_type):
                failures.append(f"default_public_privileges_present:{object_type}")

    return {
        "ok": not failures,
        "database": connection.info.dbname,
        "schema": spec.schema,
        "migration_role": spec.migration_role,
        "app_role": spec.app_role,
        "objects_checked": len(objects),
        "functions_checked": len(functions),
        "failures": sorted(set(failures)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("provision", "verify"))
    parser.add_argument("--admin-url", default=os.getenv("ICODER_POSTGRES_ADMIN_URL"))
    parser.add_argument("--migration-role", default=os.getenv("ICODER_POSTGRES_MIGRATION_ROLE"))
    parser.add_argument("--app-role", default=os.getenv("ICODER_POSTGRES_APP_ROLE"))
    parser.add_argument("--schema", default=os.getenv("ICODER_POSTGRES_SCHEMA", "public"))
    parser.add_argument("--json-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.admin_url or not args.migration_role or not args.app_role:
        raise SystemExit(
            "admin URL, migration role, and app role are required via arguments or environment"
        )
    spec = RoleSpec(
        migration_role=args.migration_role,
        app_role=args.app_role,
        schema=args.schema,
        migration_password=os.getenv("ICODER_POSTGRES_MIGRATION_PASSWORD"),
        app_password=os.getenv("ICODER_POSTGRES_APP_PASSWORD"),
    )
    with psycopg.connect(normalize_postgresql_url(args.admin_url)) as connection:
        if args.command == "provision":
            provision(connection, spec)
        report = verify(connection, spec)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
