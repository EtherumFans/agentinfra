"""P1.2 Corti parity tables + drop deprecated context tables

Revision ID: 006
Revises: 005
Create Date: 2026-07-02

Closes the alembic gap surfaced by cycle 23 §5.1 / cycle 24 audit:

  Base.metadata (app.main runtime)  →  33 tables
  alembic upgrade head (001→005)    →  33 tables, but wrong shape:
                                       - 5 deprecated context_* tables
                                         (contexts, context_messages,
                                          context_task_refs,
                                          context_artifact_refs,
                                          original_input_audit) created
                                         by 005 but removed from models
                                       - 5 P1.2 Corti parity tables
                                         missing (customers, templates,
                                         tickets, password_reset_tokens,
                                         token_blacklist) — added direct
                                         to models in cycle P1.2 without
                                         a migration

After 006, `alembic upgrade head` produces the same 33-table state as
`init_db()` (Base.metadata.create_all). Prod still uses `init_db()`
(uvicorn lifespan); alembic is dev/manual only, but should be correct
for anyone who needs it (e.g. zero-downtime column adds on PostgreSQL
later).

See docs/PHASE_2_CYCLE24_ALEMBIC_GAP_AUDIT.md for the full audit and
docs/dev/BACKEND_RECOVERY.md §Prevention for the dev/prod migration
strategy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Deprecated tables to drop (created by 005, removed from models) ──────
# Listed in reverse dependency order: children first, then parents, so
# FK constraints don't block the drop. SQLite has no real FK enforcement
# by default but PostgreSQL does — order matters for prod.
_DEPRECATED_TABLES = [
    "context_artifact_refs",
    "context_task_refs",
    "context_messages",
    "contexts",
    "original_input_audit",
]


def upgrade() -> None:
    """Drop 5 deprecated context_* tables + create 5 P1.2 Corti parity tables."""

    # 1. Drop deprecated tables (IF EXISTS for safety — table may already
    # be gone if a prior init_db() ran on a fresh DB and someone then ran
    # alembic upgrade head; the deprecated tables wouldn't exist there).
    for table in _DEPRECATED_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")

    # 2. Create P1.2 Corti parity tables (mirrors model definitions in
    # app/models/customer.py, template.py, ticket.py, oauth.py).
    # Column types match Base.metadata.create_all output on SQLite —
    # sa.Enum becomes VARCHAR(N) where N = max enum value length.

    # ── customers ───────────────────────────────────────────────────
    op.create_table(
        "customers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("customer_id", sa.String(length=128), nullable=False),
        sa.Column("region", sa.Enum("us", "eu", "cn", name="customerregion"), nullable=False),
        sa.Column("nfr", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_org_id", "customers", ["organization_id"], unique=False)
    op.create_index("ix_customers_customer_id", "customers", ["customer_id"], unique=True)

    # ── templates ───────────────────────────────────────────────────
    op.create_table(
        "templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.Enum(
            "inpatient", "surgery", "outpatient", "emergency", "consultation", "custom",
            name="templatecategory",
        ), nullable=False),
        sa.Column("language", sa.Enum("zh-CN", "en-US", name="templatelanguage"), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.Enum("all_customers", "single_customer", name="templatescope"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_templates_org_id", "templates", ["organization_id"], unique=False)
    op.create_index("ix_templates_category", "templates", ["category"], unique=False)

    # ── tickets ─────────────────────────────────────────────────────
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("created_by_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("open", "in_progress", "resolved", "closed", name="ticketstatus"), nullable=False),
        sa.Column("priority", sa.Enum("low", "medium", "high", name="ticketpriority"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_org_id", "tickets", ["organization_id"], unique=False)
    op.create_index("ix_tickets_status", "tickets", ["status"], unique=False)

    # ── token_blacklist ─────────────────────────────────────────────
    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("token_hash", sa.String(length=256), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_reason", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_token_blacklist_token_hash", "token_blacklist", ["token_hash"], unique=True)
    op.create_index("ix_token_blacklist_user_id", "token_blacklist", ["user_id"], unique=False)

    # ── password_reset_tokens ───────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    """Reverse: drop the 5 P1.2 Corti parity tables + re-create 5
    deprecated context_* tables.

    The context_* re-creation mirrors migration 005's schema so the chain
    is reversible. Best-effort — production downgrades are rare and
    typically only need the table shells for archive/restore.
    """
    # 1. Drop P1.2 Corti parity tables (reverse order of upgrade)
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_token_blacklist_user_id", table_name="token_blacklist")
    op.drop_index("ix_token_blacklist_token_hash", table_name="token_blacklist")
    op.drop_table("token_blacklist")

    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_org_id", table_name="tickets")
    op.drop_table("tickets")

    op.drop_index("ix_templates_category", table_name="templates")
    op.drop_index("ix_templates_org_id", table_name="templates")
    op.drop_table("templates")

    op.drop_index("ix_customers_customer_id", table_name="customers")
    op.drop_index("ix_customers_org_id", table_name="customers")
    op.drop_table("customers")

    # 2. Re-create deprecated context_* tables (mirror 005's schema).
    # Use IF NOT EXISTS to avoid collision if the downgrade runs against
    # a DB where the tables still exist.
    # Schema copied from alembic/versions/005_context_tables.py.
    op.execute("""
        CREATE TABLE IF NOT EXISTS contexts (
            id VARCHAR NOT NULL,
            context_id VARCHAR(64) NOT NULL,
            organization_id VARCHAR(12),
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (context_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS context_messages (
            id VARCHAR NOT NULL,
            context_id VARCHAR NOT NULL,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS context_task_refs (
            id VARCHAR NOT NULL,
            context_id VARCHAR NOT NULL,
            task_id VARCHAR NOT NULL,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS context_artifact_refs (
            id VARCHAR NOT NULL,
            context_id VARCHAR NOT NULL,
            artifact_id VARCHAR NOT NULL,
            artifact_type VARCHAR(32) NOT NULL,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS original_input_audit (
            id VARCHAR NOT NULL,
            context_id VARCHAR NOT NULL,
            original_input TEXT NOT NULL,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
            PRIMARY KEY (id)
        )
    """)
