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

1. Backfills every NULL / empty organization_id row in
   encounters, documents, cdi_cases to the canonical dev/test
   org ``org_default1``. Pre-migration counts on
   ``data/icoder.db`` (2026-07-19):

       encounters  10 NULL → 10 backfilled
       documents   22 NULL → 22 backfilled
       cdi_cases  718 NULL → 718 backfilled

   The default ``org_default1`` is the same org Gate 2 used
   for legacy system-scope rows. In production, the same
   pattern applies with the deployment's actual default org;
   the backfill constant is configurable via env var
   ``ICODER_BACKFILL_DEFAULT_ORG`` (defaults to ``org_default1``
   for dev parity).

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

Backwards compatibility: NULL rows are eliminated by the
backfill before the constraint is added, so the CHECK passes
immediately on all rows. The downgrade reverses the constraint
additions but does NOT undo the backfill (the original NULL
state is not recoverable from the row alone).
"""
from __future__ import annotations

import os
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


def _default_org() -> str:
    """The org id to use for backfilling NULL organization_id rows."""
    return os.environ.get("ICODER_BACKFILL_DEFAULT_ORG", "org_default1")


def upgrade() -> None:
    bind = op.get_bind()
    default_org = _default_org()

    # ── §1 Backfill NULL / empty organization_id ──────────────────
    # Some legacy rows have empty string instead of NULL — both
    # must be normalised before the NOT NULL constraint lands.
    for table in _CLINICAL_TABLES:
        result = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE organization_id IS NULL OR organization_id = ''"
            )
        )
        null_count = result.scalar() or 0
        if null_count > 0:
            bind.execute(
                sa.text(
                    f"UPDATE {table} "
                    f"SET organization_id = :org "
                    f"WHERE organization_id IS NULL OR organization_id = ''"
                ),
                {"org": default_org},
            )
            print(
                f"  [021] {table}: backfilled {null_count} NULL/empty "
                f"organization_id rows → {default_org!r}"
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
    # composite for the list-page access pattern. Skip if the index
    # already exists (defensive against partial-state DBs).
    for table in _CLINICAL_TABLES:
        try:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_index(
                    f"ix_{table}_org_created",
                    ["organization_id", "created_at"],
                )
        except Exception as e:
            print(f"  [021] {table}: index ix_{table}_org_created skipped ({e})")


def downgrade() -> None:
    # Reverse order: drop indexes, then CHECK, then NOT NULL.
    # The backfill is NOT reversed — historical NULL state is not
    # recoverable from the row alone.
    for table in _CLINICAL_TABLES:
        try:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_index(f"ix_{table}_org_created")
        except Exception:
            pass

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
