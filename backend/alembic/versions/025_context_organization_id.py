"""Phase A1B-AE-R.1.b — contexts.organization_id for cross-tenant isolation.

Revision ID: 025
Revises: 024
Create Date: 2026-07-22

A1B-AE-R.1.b closes the second half of A1B-AE Agent Runtime tech debt:

* ``contexts.organization_id`` is added (NOT NULL, default
  ``org_default1``) so the new ``DELETE /api/icoder/contexts/{id}``
  endpoint can scope by tenant and the existing Task endpoints can
  filter by org_id (cross-tenant 404 instead of leak).

This migration follows the Phase A1A Gate 2 (016) / Gate 4.2 (021)
pattern for SQLite NOT NULL additions: add the column nullable,
backfill, then batch_alter to NOT NULL.

The default ``org_default1`` matches the test bypass mock org id
(see ``tests/conftest.py::_make_mock_org``) and the dev DB's default
tenant — so rows created without an explicit org land in the same
bucket as the mock-user JWT, preserving backwards compatibility.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add contexts.organization_id (nullable → backfill → NOT NULL)."""
    # §1 — add the column nullable so existing rows survive
    op.add_column(
        "contexts",
        sa.Column(
            "organization_id",
            sa.String(12),
            nullable=True,
            comment=(
                "A1B-AE-R.1.b — tenant scope. Cross-tenant reads/writes "
                "return 404 (no leak). Default 'org_default1' matches "
                "the test-bypass mock org id."
            ),
        ),
    )

    # §2 — backfill NULLs with the canonical default
    op.execute(
        "UPDATE contexts SET organization_id = 'org_default1' "
        "WHERE organization_id IS NULL"
    )

    # §3 — index for tenant-scoped list queries
    op.create_index(
        "idx_contexts_organization_id",
        "contexts",
        ["organization_id"],
    )

    # §4 — NOT NULL via batch_alter_table (SQLite can't ALTER COLUMN directly)
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.alter_column(
            "organization_id",
            existing_type=sa.String(12),
            nullable=False,
            existing_server_default=sa.text("'org_default1'"),
        )


def downgrade() -> None:
    """Reverse: drop the column (backfill is not recoverable)."""
    op.drop_index("idx_contexts_organization_id", table_name="contexts")
    with op.batch_alter_table("contexts") as batch_op:
        batch_op.drop_column("organization_id")
