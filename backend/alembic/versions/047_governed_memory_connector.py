"""Add governed persistent memory consent and retention metadata.

Revision ID: 047
Revises: 046
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_consents",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("agent_id", sa.String(length=12), nullable=False),
        sa.Column("purpose_of_use", sa.String(length=32), nullable=False),
        sa.Column("legal_basis", sa.String(length=32), nullable=False, server_default="user-consent"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=12), nullable=False),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", "agent_id", "purpose_of_use",
            name="uq_memory_consent_subject_agent_purpose",
        ),
    )
    op.create_index("ix_memory_consents_organization_id", "memory_consents", ["organization_id"])
    op.create_index("ix_memory_consents_user_id", "memory_consents", ["user_id"])
    op.create_index("ix_memory_consents_agent_id", "memory_consents", ["agent_id"])
    op.create_index("ix_memory_consents_expires_at", "memory_consents", ["expires_at"])

    with op.batch_alter_table("conversation_memories") as batch:
        batch.add_column(sa.Column("consent_id", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("actor_type", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("actor_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("purpose_of_use", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("content_digest", sa.String(length=64), nullable=True))
        batch.create_foreign_key(
            "fk_conversation_memories_consent_id", "memory_consents",
            ["consent_id"], ["id"],
        )
        batch.create_index("ix_conversation_memories_consent_id", ["consent_id"])
        batch.create_index("ix_conversation_memories_retention_until", ["retention_until"])


def downgrade() -> None:
    with op.batch_alter_table("conversation_memories") as batch:
        batch.drop_index("ix_conversation_memories_retention_until")
        batch.drop_index("ix_conversation_memories_consent_id")
        batch.drop_constraint("fk_conversation_memories_consent_id", type_="foreignkey")
        batch.drop_column("content_digest")
        batch.drop_column("retention_until")
        batch.drop_column("purpose_of_use")
        batch.drop_column("actor_id")
        batch.drop_column("actor_type")
        batch.drop_column("consent_id")
    op.drop_table("memory_consents")
