"""Phase 1 Context tables (SPEC §4.3)

Revision ID: 005
Revises: 004
Create Date: 2026-06-20

Adds the Context, ContextMessage, ContextTaskRef, ContextArtifactRef,
and OriginalInputAudit tables that back the server-side per-session
store. Strict isolation (Q4): every child row FKs back to
``contexts.id`` with ``ON DELETE CASCADE``; the audit table is
deliberately separate and has its own retention window.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 4 Context tables + 1 original_input_audit table."""
    op.create_table(
        "contexts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("redacted_input_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("original_input_ref", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("idx_contexts_expires_at", "contexts", ["expires_at"])
    op.create_index("idx_contexts_agent_id", "contexts", ["agent_id"])
    op.create_index("idx_contexts_status", "contexts", ["status"])

    op.create_table(
        "context_messages",
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("parts_json", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column(
            "redacted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "metadata_json",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["contexts.id"],
            name="fk_context_messages_context_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("context_id", "message_id"),
    )

    op.create_table(
        "context_task_refs",
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["contexts.id"],
            name="fk_context_task_refs_context_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("context_id", "task_id"),
    )

    op.create_table(
        "context_artifact_refs",
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_id"],
            ["contexts.id"],
            name="fk_context_artifact_refs_context_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("context_id", "artifact_id"),
    )

    op.create_table(
        "original_input_audit",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("original_input", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("retention_until", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_original_input_audit_context_id",
        "original_input_audit",
        ["context_id"],
    )
    op.create_index(
        "idx_original_input_audit_retention",
        "original_input_audit",
        ["retention_until"],
    )


def downgrade() -> None:
    """Drop the 5 tables (reverse order)."""
    op.drop_index(
        "idx_original_input_audit_retention", table_name="original_input_audit"
    )
    op.drop_index(
        "idx_original_input_audit_context_id", table_name="original_input_audit"
    )
    op.drop_table("original_input_audit")

    op.drop_table("context_artifact_refs")
    op.drop_table("context_task_refs")
    op.drop_table("context_messages")

    op.drop_index("idx_contexts_status", table_name="contexts")
    op.drop_index("idx_contexts_agent_id", table_name="contexts")
    op.drop_index("idx_contexts_expires_at", table_name="contexts")
    op.drop_table("contexts")
