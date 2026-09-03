"""Persist encrypted, tenant-scoped Guided Documents.

Revision ID: 036
Revises: 035
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guided_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=True),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("template_version_id", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("encrypted_string_document_json", sa.Text(), nullable=False),
        sa.Column("encrypted_structured_document_json", sa.Text(), nullable=True),
        sa.Column("encrypted_labels_json", sa.Text(), nullable=False),
        sa.Column("encrypted_classic_sections_json", sa.Text(), nullable=True),
        sa.Column("credits_consumed", sa.Float(), nullable=False),
        sa.Column("is_stream", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "owner_id", "document_id",
            name="uq_guided_document_scope",
        ),
    )
    for column in ("organization_id", "owner_id", "interaction_id", "document_id"):
        op.create_index(
            f"ix_guided_documents_{column}",
            "guided_documents",
            [column],
            unique=False,
        )
    op.create_table(
        "guided_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("section_id", sa.String(length=64), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("encrypted_definition_json", sa.Text(), nullable=False),
        sa.Column("auto_generated", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "section_id", name="uq_guided_section_scope"
        ),
    )
    for column in ("organization_id", "owner_id", "section_id"):
        op.create_index(
            f"ix_guided_sections_{column}",
            "guided_sections",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("guided_sections")
    op.drop_table("guided_documents")
