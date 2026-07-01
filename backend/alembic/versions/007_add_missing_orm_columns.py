"""Add 6 ORM-declared columns missing from DB

Revision ID: 007
Revises: 006
Create Date: 2026-07-02

Closes the column-level schema gap surfaced by /qa 2026-07-02 (ISSUE-001):
cycle 24's table-level migration 006 closed the table gap (drop context_*,
create P1.2 gap tables) but left column-level gaps open — the ORM declared
columns that no migration ever added to the DB. Any query selecting these
columns blew up with sqlite3.OperationalError "no such column".

6 missing columns across 3 tables, all the same class of bug:

  users.token_version           (int, default 0, NOT NULL)
  audit_logs.agent_id           (String(128), nullable, indexed)
  audit_logs.agent_account_id   (String(12),  nullable)
  audit_logs.delegated_by_user_id (String(64), nullable)
  coding_reviews.evidence_ranking         (JSON, nullable)
  coding_reviews.confidence_calibration   (JSON, nullable)

users.token_version is the user-facing one — it broke registration, login,
token refresh, and revoke-tokens. The other 5 would surface as 500s in
audit-logging and coding-review codepaths.

SQLite supports ADD COLUMN; PostgreSQL needs the usual NOT NULL-with-default
dance. server_default='0' on token_version makes the migration safe on a
populated users table (existing rows backfilled to 0).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users.token_version — NOT NULL int, default 0
    # server_default so existing rows (if any) backfill to 0.
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # audit_logs — 3 nullable string columns
    op.add_column(
        "audit_logs",
        sa.Column("agent_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("agent_account_id", sa.String(length=12), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("delegated_by_user_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_audit_logs_agent_id",
        "audit_logs",
        ["agent_id"],
        unique=False,
    )

    # coding_reviews — 2 nullable JSON columns
    op.add_column(
        "coding_reviews",
        sa.Column("evidence_ranking", sa.JSON(), nullable=True),
    )
    op.add_column(
        "coding_reviews",
        sa.Column("confidence_calibration", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coding_reviews", "confidence_calibration")
    op.drop_column("coding_reviews", "evidence_ranking")

    op.drop_index("ix_audit_logs_agent_id", table_name="audit_logs")
    op.drop_column("audit_logs", "delegated_by_user_id")
    op.drop_column("audit_logs", "agent_account_id")
    op.drop_column("audit_logs", "agent_id")

    op.drop_column("users", "token_version")
