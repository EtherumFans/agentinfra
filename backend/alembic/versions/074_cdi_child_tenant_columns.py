"""Align tenant columns at the Alembic head with the fail-closed ORM.

Revision ID: 074
Revises: 073
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


_CHILD_TABLES = {
    "cdi_documentation_gaps": "case_id",
    "cdi_provider_queries": "case_id",
    "cdi_clinician_responses": "case_id",
    "cdi_document_versions": "case_id",
}
_EXISTING_TENANT_TABLES = (
    "clinical_evidences",
    "code_candidates",
    "coding_reviews",
    "api_keys",
    "team_members",
    "team_invites",
    "oauth_clients",
    "oauth_tokens",
    "coding_review_runs",
)
_WIDE_TENANT_TABLES = ("clinical_facts", "guided_documents", "guided_sections")


def _reject_unattributed(bind, tables: tuple[str, ...]) -> None:
    bad = []
    for table in tables:
        count = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} "
            "WHERE organization_id IS NULL OR organization_id = ''"
        )).scalar() or 0
        if count:
            bad.append(f"{table}={count}")
    if bad:
        raise RuntimeError(
            "migration 074 requires evidence-backed tenant reconciliation: "
            + ", ".join(bad)
        )


def upgrade() -> None:
    bind = op.get_bind()
    for table in _CHILD_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("organization_id", sa.String(12), nullable=True))
    for table, case_column in _CHILD_TABLES.items():
        bind.execute(sa.text(
            f"UPDATE {table} SET organization_id = "
            f"(SELECT organization_id FROM cdi_cases WHERE cdi_cases.id = {table}.{case_column}) "
            "WHERE organization_id IS NULL"
        ))

    all_fail_closed = tuple(_CHILD_TABLES) + _EXISTING_TENANT_TABLES
    _reject_unattributed(bind, all_fail_closed)
    for table in all_fail_closed:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "organization_id", existing_type=sa.String(12), nullable=False
            )
    for table in _CHILD_TABLES:
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])

    for table in _WIDE_TENANT_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.String(64),
                type_=sa.String(12),
                nullable=False,
            )


def downgrade() -> None:
    for table in _WIDE_TENANT_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.String(12),
                type_=sa.String(64),
                nullable=False,
            )
    for table in _EXISTING_TENANT_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "organization_id", existing_type=sa.String(12), nullable=True
            )
    for table in reversed(tuple(_CHILD_TABLES)):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("organization_id")
