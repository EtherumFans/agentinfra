"""M3-0 hospital pilot: coding_review_runs table

Revision ID: 004
Revises: 003
Create Date: 2026-06-11

Adds the persistent state table for the Medical Coding Review Agent
(MedCodER 5-stage pipeline, ``icoder/medcoder-coding-review-agent@1.0.0``).
Replaces the in-memory ``_RUNS_STORE: dict`` previously used by
``app.api.icoder_coding_review``.

Phase D3 (2026-06-26): the legacy 14-stage ``homepage-coding-review``
agent has been removed; the agent_ref stored in this table is now the
MedCodER agent_ref. Existing rows from before Phase D3 still reference
the legacy ``icoder/homepage-coding-review-agent@1.0.0`` string and
remain readable (the column is just a string identifier).

Schema notes
------------
* PK is 24-char hex (matches the API ``run_id``) so external clients can
  correlate the API run_id with the DB row without a second lookup.
* JSON columns are used liberally for forward-compatible schema evolution —
  the M3-0 workbench already reads most of these as dicts, and adding new
  optional keys (e.g. ``pipeline_stage_meta`` in Commit 6) should not
  require a migration.
* Indices: ``(organization_id, created_at)`` for tenant-scoped time-window
  queries, plus ``case_id`` and ``trace_id`` lookups, and ``status`` for
  ops dashboards.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create coding_review_runs table (M3-0 pipeline persistence)."""
    # SQLite-friendly: op.create_table works on both backends.
    op.create_table(
        "coding_review_runs",
        sa.Column("id", sa.String(length=24), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),

        sa.Column("organization_id", sa.String(length=12), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=True),

        sa.Column("agent_ref", sa.String(length=128), nullable=False),
        sa.Column("agent_category", sa.String(length=64), nullable=False, server_default="official_reference_agent"),
        sa.Column("prediction_mode", sa.String(length=32), nullable=False, server_default="link_validation"),

        sa.Column("case_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("input_source", sa.String(length=32), nullable=False, server_default="manual"),

        sa.Column("status", sa.String(length=32), nullable=False, server_default="unavailable"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("business_result_generated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("reason", sa.String(length=512), nullable=False, server_default=""),

        sa.Column("primary_diagnosis", sa.JSON(), nullable=True),
        sa.Column("secondary_diagnoses", sa.JSON(), nullable=False),
        sa.Column("procedures", sa.JSON(), nullable=False),
        sa.Column("high_risk_coding_points", sa.JSON(), nullable=False),
        sa.Column("evidence_chain", sa.JSON(), nullable=False),
        sa.Column("risk_route", sa.JSON(), nullable=False),
        sa.Column("safety_gate", sa.JSON(), nullable=False),
        sa.Column("drg_route", sa.JSON(), nullable=True),
        sa.Column("pipeline_stages_observed", sa.JSON(), nullable=False),
        sa.Column("pipeline_stage_meta", sa.JSON(), nullable=True),

        sa.Column("human_review_records", sa.JSON(), nullable=False),

        sa.Column("encounter_text", sa.Text(), nullable=True),
        sa.Column("encounter_text_redacted", sa.Text(), nullable=True),

        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("code_dict_version", sa.String(length=64), nullable=True),
        sa.Column("rule_version", sa.String(length=64), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("data_asset_version", sa.String(length=64), nullable=True),

        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_coding_review_runs_organization_id",
        ),
    )

    op.create_index(
        op.f("ix_coding_review_runs_organization_id"),
        "coding_review_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coding_review_runs_created_by_user_id"),
        "coding_review_runs",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coding_review_runs_case_id"),
        "coding_review_runs",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coding_review_runs_trace_id"),
        "coding_review_runs",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_coding_review_runs_org_created",
        "coding_review_runs",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_coding_review_runs_status"),
        "coding_review_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop coding_review_runs table (M3-0 pipeline persistence)."""
    op.drop_index(op.f("ix_coding_review_runs_status"), table_name="coding_review_runs")
    op.drop_index("ix_coding_review_runs_org_created", table_name="coding_review_runs")
    op.drop_index(op.f("ix_coding_review_runs_trace_id"), table_name="coding_review_runs")
    op.drop_index(op.f("ix_coding_review_runs_case_id"), table_name="coding_review_runs")
    op.drop_index(op.f("ix_coding_review_runs_created_by_user_id"), table_name="coding_review_runs")
    op.drop_index(op.f("ix_coding_review_runs_organization_id"), table_name="coding_review_runs")
    op.drop_table("coding_review_runs")
