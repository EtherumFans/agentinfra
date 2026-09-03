"""Persist encrypted, tenant-scoped Facts API records.

Revision ID: 035
Revises: 034
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=False),
        sa.Column("fact_id", sa.String(length=64), nullable=False),
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("group_key", sa.String(length=96), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("is_discarded", sa.Boolean(), nullable=False),
        sa.Column("encrypted_text", sa.Text(), nullable=False),
        sa.Column("encrypted_evidence_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "owner_id",
            "interaction_id",
            "fact_id",
            name="uq_clinical_fact_scope",
        ),
    )
    for column in ("organization_id", "owner_id", "interaction_id", "fact_id"):
        op.create_index(
            f"ix_clinical_facts_{column}",
            "clinical_facts",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("clinical_facts")
