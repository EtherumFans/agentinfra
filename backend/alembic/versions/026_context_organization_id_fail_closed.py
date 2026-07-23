"""Phase A1B-AE-RV.2 — contexts.organization_id fail-closed.

Revision ID: 026
Revises: 025
Create Date: 2026-07-23

A1B-AE-RV.2 closes Gap 12 from the terminal correction notice:
Migration 025 set ``existing_server_default=sa.text("'org_default1'")``
which combined with the ORM ``server_default='org_default1'`` meant
new writes could land in the ``org_default1`` bucket silently when
the caller forgot to pass ``current_org.id``.

RV.2 removes the permanent server_default so missing organization_id
on insert fails closed (NOT NULL violation) instead of falling back.
The ORM model in ``db_models.py`` was updated in the same sub-gate
to drop both ``default`` and ``server_default``.

Existing rows keep their materialized ``organization_id`` value
(``org_default1`` for historical rows; real org id for newer rows).
The CHECK constraint is not affected — NOT NULL is still enforced.

PostgreSQL note: ``batch_alter_table`` is a SQLite-only pattern; on
PostgreSQL alembic emits a server-side ``ALTER COLUMN DROP DEFAULT``
which is a no-op if no default is set. Verified by syntactic
inspection; runtime PG verification deferred per Gate 3R.0 §19
(no psql/asyncpg/testcontainers in this environment).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop permanent server_default from contexts.organization_id.

    Use batch_alter_table so SQLite (no direct ALTER COLUMN) and
    PostgreSQL (direct ALTER COLUMN) both work. The existing_server_default
    hint tells alembic what to drop; if no default is present, this
    is a no-op on PostgreSQL.
    """
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.alter_column(
            "organization_id",
            existing_type=sa.String(12),
            nullable=False,
            server_default=None,  # drop the permanent 'org_default1' default
            existing_server_default=sa.text("'org_default1'"),
        )


def downgrade() -> None:
    """Restore the permanent default (back-compat for older clients)."""
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.alter_column(
            "organization_id",
            existing_type=sa.String(12),
            nullable=False,
            server_default=sa.text("'org_default1'"),
        )
