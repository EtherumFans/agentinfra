"""Phase A1A Gate 4.2 — Clinical tables tenant NOT NULL + CHECK.

Revision ID: 021
Revises: 020
Create Date: 2026-07-19

Closes charter §4.2 carry-over GATE3_015: encounters, documents,
and cdi_cases had nullable organization_id with no DB-level
enforcement. Gate 3.7 (Migration 019) added CHECK constraints
only on run_history and audit_logs; the clinical tables were
deferred to "Phase B" — Gate 4.2 takes ownership because these
tables are on the PHI critical path and cannot wait.

This migration:

1. Refuses to proceed if any NULL / empty organization_id row remains in
   encounters, documents or cdi_cases. Historical development evidence was:

       encounters  10 NULL
       documents   22 NULL
       cdi_cases  718 NULL

   Those rows require evidence-backed operator reconciliation before upgrade;
   assigning unknown clinical data to a default tenant is forbidden.

2. Adds a NOT NULL constraint on organization_id for each
   table via batch_alter_table. SQLite doesn't support
   ALTER COLUMN SET NOT NULL directly; batch_alter_table
   recreates the table with the new constraint.

3. Adds a CHECK constraint:
   ``organization_id IS NOT NULL``
   This is structurally redundant with NOT NULL but exists
   as an explicit second layer of defence (NOT NULL can be
   silently dropped by a future batch_alter_table pass that
   forgets to re-add it; the CHECK is harder to remove
   accidentally).

The downgrade reverses the constraint additions but never changes tenant
attribution data.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CLINICAL_TABLES: tuple[str, ...] = (
    "encounters",
    "documents",
    "cdi_cases",
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── §1 Refuse unattributed clinical rows ───────────────────────
    # Assigning unknown PHI rows to a default tenant is a cross-tenant data
    # breach. Operators must reconcile them from source evidence before this
    # migration can proceed.
    unattributed: dict[str, int] = {}
    for table in _CLINICAL_TABLES:
        result = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE organization_id IS NULL OR organization_id = ''"
            )
        )
        null_count = result.scalar() or 0
        if null_count:
            unattributed[table] = int(null_count)
    if unattributed:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(unattributed.items())
        )
        raise RuntimeError(
            "migration 021 requires evidence-backed clinical tenant "
            "reconciliation: " + details
        )

    # ── §2 NOT NULL + CHECK on organization_id ────────────────────
    # SQLite needs batch_alter_table for column constraint changes.
    # On Postgres this is a plain ALTER COLUMN SET NOT NULL + ADD
    # CONSTRAINT.
    for table in _CLINICAL_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.String(12),
                nullable=False,
            )
            batch_op.create_check_constraint(
                f"chk_{table}_org_not_null",
                condition="organization_id IS NOT NULL",
            )

    # ── §3 Index for tenant-scoped list queries ──────────────────
    # Most clinical list endpoints filter by (organization_id, created_at).
    # The existing index on organization_id is retained; this adds a
    # composite for the list-page access pattern. Inspect before DDL: catching
    # a duplicate-object exception would leave PostgreSQL's transaction in an
    # aborted state.
    for table in _CLINICAL_TABLES:
        index_name = f"ix_{table}_org_created"
        existing = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
        if index_name not in existing:
            op.create_index(
                index_name, table, ["organization_id", "created_at"],
            )


def downgrade() -> None:
    # Reverse order: drop indexes, then CHECK, then NOT NULL.
    bind = op.get_bind()
    for table in _CLINICAL_TABLES:
        index_name = f"ix_{table}_org_created"
        existing = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table)

    for table in _CLINICAL_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(
                f"chk_{table}_org_not_null", type_="check",
            )
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.String(12),
                nullable=True,
            )
