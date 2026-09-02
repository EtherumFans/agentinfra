"""Permit dual-read v1/v2 PHI envelopes for online HSM rotation.

Revision ID: 072
Revises: 071
Create Date: 2026-09-02
"""

from __future__ import annotations

import re

from alembic import op


revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
V1_PATTERN = r"^v[1-9][0-9]*:gAAAAA[A-Za-z0-9_-]{90,}={0,2}$"
V2_PATTERN = r"^v2:[A-Za-z0-9_-]{160,}$"


def _quoted(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise RuntimeError("revision 072 found an invalid PHI constraint identifier")
    return f'"{value}"'


def _constraints() -> list[tuple[str, str, str]]:
    rows = op.get_bind().exec_driver_sql(
        "SELECT con.conname, cls.relname, att.attname "
        "FROM pg_constraint con "
        "JOIN pg_class cls ON cls.oid=con.conrelid "
        "JOIN pg_namespace ns ON ns.oid=cls.relnamespace "
        "JOIN LATERAL unnest(con.conkey) key(attnum) ON true "
        "JOIN pg_attribute att ON att.attrelid=cls.oid AND att.attnum=key.attnum "
        "WHERE ns.nspname=current_schema() AND con.contype='c' "
        "AND con.conname LIKE 'ck_phi_envelope_%%' "
        "ORDER BY con.conname"
    ).all()
    result = [(str(row[0]), str(row[1]), str(row[2])) for row in rows]
    if len(result) != 71 or len({row[0] for row in result}) != 71:
        raise RuntimeError(
            f"revision 072 requires exactly 71 single-column PHI constraints; found {len(result)}"
        )
    return result


def _replace(pattern: str) -> None:
    bind = op.get_bind()
    for constraint, table, column in _constraints():
        bind.exec_driver_sql(
            f"ALTER TABLE {_quoted(table)} DROP CONSTRAINT {_quoted(constraint)}"
        )
        bind.exec_driver_sql(
            f"ALTER TABLE {_quoted(table)} ADD CONSTRAINT {_quoted(constraint)} CHECK ("
            f"{_quoted(column)} IS NULL OR {_quoted(column)} = '' OR "
            f"{_quoted(column)} ~ '{pattern}')"
        )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _replace(f"({V1_PATTERN})|({V2_PATTERN})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    bind = op.get_bind()
    constraints = _constraints()
    organizations = bind.exec_driver_sql(
        "SELECT id FROM organizations ORDER BY id"
    ).scalars().all()
    for organization_id in organizations:
        bind.exec_driver_sql(
            "SELECT set_config('icoder.current_organization_id', %s, true)",
            (organization_id,),
        )
        for _constraint, table, column in constraints:
            count = bind.exec_driver_sql(
                f"SELECT count(*) FROM {_quoted(table)} WHERE {_quoted(column)} LIKE 'v2:%%' "
                f"AND {_quoted(column)} NOT LIKE 'v2:gAAAAA%%'"
            ).scalar_one()
            if int(count):
                raise RuntimeError(
                    "revision 072 refuses downgrade while HSM v2 PHI remains; "
                    "run controlled reverse rotation to v1 first"
                )
    _replace(V1_PATTERN)
