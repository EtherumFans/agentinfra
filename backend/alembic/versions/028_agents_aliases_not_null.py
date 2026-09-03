"""Set agents.aliases NOT NULL

Phase A1C.2 (2026-07-25): closes the last schema drift detected by
test_no_schema_drift_against_fresh_alembic_db at HEAD post-Migration 027.

The ORM model declares:
    aliases: Mapped[list] = mapped_column(JSON, default=list)

`Mapped[list]` (no Optional) makes SQLAlchemy infer nullable=False, but
Migration 023 created the column without explicit nullable=False, leaving
the DB column nullable=True. This Migration 028 ALTERs the column to
NOT NULL — relying on the Agent.before_insert event listener to populate
defaults (see app.models.agent._agent_before_insert) so existing NULLs
are not present in production data.

Safe for SQLite (batch_alter_table rebuild) and PostgreSQL (ALTER COLUMN
... SET NOT NULL).

Revision ID: 028
Revises: 027
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Backfill any pre-existing NULLs before SET NOT NULL
    bind.execute(
        sa.text(
            "UPDATE agents SET aliases = '[]' WHERE aliases IS NULL"
        )
    )

    if dialect == "sqlite":
        with op.batch_alter_table("agents") as batch_op:
            batch_op.alter_column(
                column_name="aliases",
                type_=sa.JSON(),
                existing_type=sa.JSON(),
                nullable=False,
            )
    else:
        op.alter_column(
            table_name="agents",
            column_name="aliases",
            type_=sa.JSON(),
            existing_type=sa.JSON(),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("agents") as batch_op:
            batch_op.alter_column(
                column_name="aliases",
                type_=sa.JSON(),
                existing_type=sa.JSON(),
                nullable=True,
            )
    else:
        op.alter_column(
            table_name="agents",
            column_name="aliases",
            type_=sa.JSON(),
            existing_type=sa.JSON(),
            nullable=True,
        )
