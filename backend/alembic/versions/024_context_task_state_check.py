"""Phase A1B-AE-R.1.a — context_task_refs.state CHECK constraint.

Revision ID: 024
Revises: 023
Create Date: 2026-07-22

A1B-AE-R.1.a lands the Task state machine at the DB level:

* ``context_task_refs.state`` is restricted to the 5 A2A v0.3 Task states
  (``submitted``, ``working``, ``completed``, ``failed``, ``canceled``).

Migration 006 (P1.2) dropped the 5 context_* tables because the P1.2
runtime no longer persisted Context server-side. A1B-AE.5 re-introduced
the SQLAlchemy models in ``db_models.py`` but did not restore the
tables at the alembic level — every test that hit ``init_db()`` got
the tables via Base.metadata, but the alembic chain stayed gap-ful.

A1B-AE-R.1.a closes that gap: this migration re-creates the 5 context
tables when they are absent and bakes the CHECK constraint straight into
``context_task_refs``.  SQLAlchemy types keep this migration portable
between the supported SQLite development path and PostgreSQL production.

Downgrading reverses the order: drops the 5 tables (matching 006's
behaviour) so the schema is logically back at the A1B-AE.11 state.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recreate 5 context_* tables + CHECK on context_task_refs.state."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("contexts"):
        op.create_table(
            "contexts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("agent_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False),
            sa.Column(
                "redacted_input_hash", sa.String(length=64),
                nullable=False, server_default="",
            ),
            sa.Column(
                "original_input_ref", sa.String(length=64),
                nullable=False, server_default="",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_contexts_expires_at", "contexts", ["expires_at"])
        op.create_index("idx_contexts_agent_id", "contexts", ["agent_id"])
        op.create_index("idx_contexts_status", "contexts", ["status"])

    if not inspector.has_table("context_messages"):
        op.create_table(
            "context_messages",
            sa.Column("context_id", sa.String(length=36), nullable=False),
            sa.Column("message_id", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("parts_json", sa.Text(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column(
                "redacted", sa.Boolean(), nullable=False,
                server_default=sa.true(),
            ),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("context_id", "message_id"),
        )

    if not inspector.has_table("context_task_refs"):
        op.create_table(
            "context_task_refs",
            sa.Column("context_id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "state IN ('submitted', 'working', 'completed', 'failed', 'canceled')",
                name="ck_context_task_refs_state",
            ),
            sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("context_id", "task_id"),
        )

    if not inspector.has_table("context_artifact_refs"):
        op.create_table(
            "context_artifact_refs",
            sa.Column("context_id", sa.String(length=36), nullable=False),
            sa.Column("artifact_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=False),
            sa.Column("url", sa.String(length=1024), nullable=False),
            sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("context_id", "artifact_id"),
        )

    if not inspector.has_table("original_input_audit"):
        op.create_table(
            "original_input_audit",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("context_id", sa.String(length=36), nullable=False),
            sa.Column("original_input", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("retention_until", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_original_input_audit_context_id", "original_input_audit", ["context_id"]
        )
        op.create_index(
            "idx_original_input_audit_retention", "original_input_audit", ["retention_until"]
        )


def downgrade() -> None:
    """Drop the 5 context_* tables (matches migration 006 behaviour)."""
    inspector = sa.inspect(op.get_bind())
    for table_name in (
        "original_input_audit",
        "context_artifact_refs",
        "context_task_refs",
        "context_messages",
        "contexts",
    ):
        if inspector.has_table(table_name):
            op.drop_table(table_name)
