"""Expand stable Agent identifiers and their foreign keys to varchar(128).

The public, built-in Agent keys include values such as
``medical-coding-agent``.  Migration 027 incorrectly narrowed ``agents.id``
to the 12-character internal-ID convention, which SQLite does not enforce but
PostgreSQL does.

Revision ID: 075
Revises: 074
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


CHILD_COLUMNS = (
    ("agent_connectors", "agent_id", False),
    ("agent_connectors", "target_agent_id", True),
    ("memory_consents", "agent_id", False),
    ("conversation_memories", "agent_id", True),
)


def _alter_columns(length: int) -> None:
    bind = op.get_bind()
    target_type = sa.String(length=length)
    existing_type = sa.String(length=12 if length == 128 else 128)

    if bind.dialect.name == "sqlite":
        for table, column, nullable in CHILD_COLUMNS:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(
                    column,
                    type_=target_type,
                    existing_type=existing_type,
                    existing_nullable=nullable,
                )
        with op.batch_alter_table("agents") as batch:
            batch.alter_column(
                "id",
                type_=target_type,
                existing_type=existing_type,
                existing_nullable=False,
            )
        return

    for table, column, nullable in CHILD_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=target_type,
            existing_type=existing_type,
            existing_nullable=nullable,
        )
    op.alter_column(
        "agents",
        "id",
        type_=target_type,
        existing_type=existing_type,
        existing_nullable=False,
    )


def _drop_postgresql_foreign_keys() -> None:
    for constraint, table in (
        ("fk_agent_connectors_agent_scope", "agent_connectors"),
        ("fk_agent_connectors_target_agent_scope", "agent_connectors"),
        ("memory_consents_agent_id_fkey", "memory_consents"),
        ("conversation_memories_agent_id_fkey", "conversation_memories"),
    ):
        op.drop_constraint(constraint, table, type_="foreignkey")


def _create_postgresql_foreign_keys() -> None:
    op.create_foreign_key(
        "fk_agent_connectors_agent_scope",
        "agent_connectors",
        "agents",
        ["organization_id", "agent_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_agent_connectors_target_agent_scope",
        "agent_connectors",
        "agents",
        ["organization_id", "target_agent_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "memory_consents_agent_id_fkey",
        "memory_consents",
        "agents",
        ["agent_id"],
        ["id"],
    )
    op.create_foreign_key(
        "conversation_memories_agent_id_fkey",
        "conversation_memories",
        "agents",
        ["agent_id"],
        ["id"],
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _drop_postgresql_foreign_keys()
    _alter_columns(128)
    if op.get_bind().dialect.name == "postgresql":
        _create_postgresql_foreign_keys()


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, _nullable in (("agents", "id", False), *CHILD_COLUMNS):
        too_long = bind.execute(
            sa.text(
                f'SELECT COUNT(*) FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL AND length("{column}") > 12'
            )
        ).scalar_one()
        if too_long:
            raise RuntimeError(
                f"cannot downgrade 075: {table}.{column} contains "
                f"{too_long} Agent identifier(s) longer than 12 characters"
            )

    if bind.dialect.name == "postgresql":
        _drop_postgresql_foreign_keys()
    _alter_columns(12)
    if bind.dialect.name == "postgresql":
        _create_postgresql_foreign_keys()
