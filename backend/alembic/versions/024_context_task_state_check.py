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
tables (using ``CREATE TABLE IF NOT EXISTS`` so the init_db path is
unaffected) and bakes the CHECK constraint straight into the
``context_task_refs`` DDL. No ``ALTER TABLE`` is issued, so SQLite's
no-ALTER limitation does not apply.

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
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contexts (
            id VARCHAR(36) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            agent_id VARCHAR(128) NOT NULL,
            status VARCHAR(16) NOT NULL,
            metadata_json TEXT NOT NULL,
            redacted_input_hash VARCHAR(64) NOT NULL DEFAULT '',
            original_input_ref VARCHAR(64) NOT NULL DEFAULT '',
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_contexts_expires_at ON contexts (expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_contexts_agent_id ON contexts (agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_contexts_status ON contexts (status)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS context_messages (
            context_id VARCHAR(36) NOT NULL,
            message_id VARCHAR(64) NOT NULL,
            role VARCHAR(32) NOT NULL,
            parts_json TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            redacted BOOLEAN NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (context_id, message_id),
            FOREIGN KEY(context_id) REFERENCES contexts (id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS context_task_refs (
            context_id VARCHAR(36) NOT NULL,
            task_id VARCHAR(64) NOT NULL,
            state VARCHAR(32) NOT NULL,
            started_at DATETIME NOT NULL,
            completed_at DATETIME,
            PRIMARY KEY (context_id, task_id),
            CONSTRAINT ck_context_task_refs_state
                CHECK (state IN ('submitted', 'working', 'completed', 'failed', 'canceled')),
            FOREIGN KEY(context_id) REFERENCES contexts (id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS context_artifact_refs (
            context_id VARCHAR(36) NOT NULL,
            artifact_id VARCHAR(64) NOT NULL,
            name VARCHAR(256) NOT NULL,
            mime_type VARCHAR(128) NOT NULL,
            url VARCHAR(1024) NOT NULL,
            PRIMARY KEY (context_id, artifact_id),
            FOREIGN KEY(context_id) REFERENCES contexts (id) ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS original_input_audit (
            id VARCHAR(36) NOT NULL,
            context_id VARCHAR(36) NOT NULL,
            original_input TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            retention_until DATETIME NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_original_input_audit_context_id "
        "ON original_input_audit (context_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_original_input_audit_retention "
        "ON original_input_audit (retention_until)"
    )


def downgrade() -> None:
    """Drop the 5 context_* tables (matches migration 006 behaviour)."""
    op.execute("DROP INDEX IF EXISTS idx_original_input_audit_retention")
    op.execute("DROP INDEX IF EXISTS idx_original_input_audit_context_id")
    op.execute("DROP TABLE IF EXISTS original_input_audit")
    op.execute("DROP TABLE IF EXISTS context_artifact_refs")
    op.execute("DROP TABLE IF EXISTS context_task_refs")
    op.execute("DROP TABLE IF EXISTS context_messages")
    op.execute("DROP INDEX IF EXISTS idx_contexts_status")
    op.execute("DROP INDEX IF EXISTS idx_contexts_agent_id")
    op.execute("DROP INDEX IF EXISTS idx_contexts_expires_at")
    op.execute("DROP TABLE IF EXISTS contexts")
