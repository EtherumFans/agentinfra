"""Set coding_review_runs.created_at/updated_at to NOT NULL

Revision ID: 008
Revises: 007
Create Date: 2026-07-02

Closes the remaining schema drift surfaced by the cycle 25 schema audit.
Migration 004 created coding_review_runs with created_at/updated_at that
omitted nullable=False, so SQLite defaulted them to nullable. The ORM
model (app/models/coding_review_run.py:76-79) declares Mapped[datetime]
which implies NOT NULL — the contract is that every run has timestamps.

This migration ALTERs both columns to NOT NULL with a server_default of
CURRENT_TIMESTAMP as a defensive backfill (there should be no NULL rows,
but if any exist they get a sane value instead of failing the ALTER).

SQLite doesn't support ALTER COLUMN directly — batch_alter_table handles
the table-rebuild dance under the hood.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("coding_review_runs") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("coding_review_runs") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        )
