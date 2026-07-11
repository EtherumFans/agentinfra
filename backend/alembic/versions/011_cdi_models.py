"""Create CDI case/gap/query/response/document_version tables (Phase 5 Track D Gate 4)

Revision ID: 011
Revises: 010
Create Date: 2026-07-11

Adds 5 tables for the China CDI capability model (PDF §6):
  - cdi_cases              — top-level CDI run per encounter
  - cdi_documentation_gaps — per-gap rows (8 gap types per §6.2)
  - cdi_provider_queries   — per-query rows (Non-leading, 9-state lifecycle per §7)
  - cdi_clinician_responses — per-response rows (clinician answers)
  - cdi_document_versions  — before/after chart snapshots for diff view

Indexes (per primary access pattern):
  - cdi_cases: (organization_id, created_at), run_id
  - cdi_documentation_gaps: case_id, gap_type, status
  - cdi_provider_queries: case_id, gap_id, lifecycle_state, clinician_user_id, sla_due_at
  - cdi_clinician_responses: query_id, is_latest, submitted_at
  - cdi_document_versions: case_id, query_id, captured_at

Schema references:
  - Domain dataclasses: app.icoder.agent_runtime.cdi.domain
  - NLQ gate: app.icoder.agent_runtime.cdi.nlq_gate (NLQ-001..009)
  - Agent pack: backend/official_agents/clinical-documentation-improvement-agent/agent_pack.json
  - Gate 4 report: reports/phase5_track_d/GATE4_DOMAIN_MODEL_REPORT.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- cdi_cases (top-level) ----
    op.create_table(
        "cdi_cases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("organization_id", sa.String(length=12), nullable=True),
        sa.Column("patient_ref", sa.String(length=128), nullable=False),
        sa.Column("encounter_ref", sa.String(length=128), nullable=False),
        sa.Column("chart_excerpt_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("chart_excerpt_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("encounter_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("draft_codes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("run_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "agent_ref",
            sa.String(length=128),
            nullable=False,
            server_default="icoder/clinical-documentation-improvement-agent@1.0.0",
        ),
        sa.Column("encounter_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("coding_specificity_checklist", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("risk_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("specialist_trace", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("completion_state", sa.String(length=32), nullable=False, server_default="REVIEW_REQUIRED"),
        sa.Column("created_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_cdi_cases_org"),
    )
    op.create_index("ix_cdi_cases_org_created", "cdi_cases", ["organization_id", "created_at"])
    op.create_index("ix_cdi_cases_patient", "cdi_cases", ["patient_ref"])
    op.create_index("ix_cdi_cases_encounter", "cdi_cases", ["encounter_ref"])
    op.create_index("ix_cdi_cases_run_id", "cdi_cases", ["run_id"])
    op.create_index("ix_cdi_cases_completion", "cdi_cases", ["completion_state"])
    op.create_index("ix_cdi_cases_created_by", "cdi_cases", ["created_by_user_id"])

    # ---- cdi_documentation_gaps ----
    op.create_table(
        "cdi_documentation_gaps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("gap_type", sa.String(length=48), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=""),
        sa.Column("minimal_clarification_needed", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_document_id", sa.String(length=256), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("evidence_char_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_char_end", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_documented_at", sa.DateTime(), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="routine"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("candidate_codes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("superseded_by_id", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cdi_cases.id"], name="fk_cdi_gaps_case"),
    )
    op.create_index("ix_cdi_gaps_case_id", "cdi_documentation_gaps", ["case_id"])
    op.create_index("ix_cdi_gaps_type", "cdi_documentation_gaps", ["gap_type"])
    op.create_index("ix_cdi_gaps_status", "cdi_documentation_gaps", ["status"])

    # ---- cdi_provider_queries ----
    op.create_table(
        "cdi_provider_queries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("gap_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=256), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("response_options", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_document_id", sa.String(length=256), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("evidence_char_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_char_end", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nlq_gate_verdict", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("nlq_gate_rules_evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nlq_gate_rules_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nlq_gate_block_reasons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("nlq_gate_version", sa.String(length=32), nullable=False, server_default="NLQ-001..009"),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="routine"),
        sa.Column("sla_due_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("viewed_at", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("cdi_specialist_user_id", sa.String(length=64), nullable=True),
        sa.Column("cdi_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("clinician_user_id", sa.String(length=64), nullable=True),
        sa.Column("created_by_agent_run_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cdi_cases.id"], name="fk_cdi_queries_case"),
        sa.ForeignKeyConstraint(["gap_id"], ["cdi_documentation_gaps.id"], name="fk_cdi_queries_gap"),
    )
    op.create_index("ix_cdi_queries_case_id", "cdi_provider_queries", ["case_id"])
    op.create_index("ix_cdi_queries_gap_id", "cdi_provider_queries", ["gap_id"])
    op.create_index("ix_cdi_queries_lifecycle", "cdi_provider_queries", ["lifecycle_state"])
    op.create_index("ix_cdi_queries_clinician", "cdi_provider_queries", ["clinician_user_id"])
    op.create_index("ix_cdi_queries_sla_due", "cdi_provider_queries", ["sla_due_at"])

    # ---- cdi_clinician_responses ----
    op.create_table(
        "cdi_clinician_responses",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("query_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("selected_option", sa.String(length=512), nullable=True),
        sa.Column("free_text_response", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("clinician_user_id", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["query_id"], ["cdi_provider_queries.id"], name="fk_cdi_responses_query"),
        sa.ForeignKeyConstraint(["case_id"], ["cdi_cases.id"], name="fk_cdi_responses_case"),
    )
    op.create_index("ix_cdi_responses_query_id", "cdi_clinician_responses", ["query_id"])
    op.create_index("ix_cdi_responses_case_id", "cdi_clinician_responses", ["case_id"])
    op.create_index("ix_cdi_responses_is_latest", "cdi_clinician_responses", ["is_latest"])
    op.create_index("ix_cdi_responses_submitted_at", "cdi_clinician_responses", ["submitted_at"])

    # ---- cdi_document_versions ----
    op.create_table(
        "cdi_document_versions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("query_id", sa.String(length=64), nullable=True),
        sa.Column("document_id", sa.String(length=256), nullable=False),
        sa.Column("document_type", sa.String(length=48), nullable=False, server_default="progress_note"),
        sa.Column("version_label", sa.String(length=32), nullable=False, server_default="initial"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["case_id"], ["cdi_cases.id"], name="fk_cdi_docvers_case"),
        sa.ForeignKeyConstraint(["query_id"], ["cdi_provider_queries.id"], name="fk_cdi_docvers_query"),
    )
    op.create_index("ix_cdi_docvers_case_id", "cdi_document_versions", ["case_id"])
    op.create_index("ix_cdi_docvers_query_id", "cdi_document_versions", ["query_id"])
    op.create_index("ix_cdi_docvers_captured_at", "cdi_document_versions", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_cdi_docvers_captured_at", table_name="cdi_document_versions")
    op.drop_index("ix_cdi_docvers_query_id", table_name="cdi_document_versions")
    op.drop_index("ix_cdi_docvers_case_id", table_name="cdi_document_versions")
    op.drop_table("cdi_document_versions")

    op.drop_index("ix_cdi_responses_submitted_at", table_name="cdi_clinician_responses")
    op.drop_index("ix_cdi_responses_is_latest", table_name="cdi_clinician_responses")
    op.drop_index("ix_cdi_responses_case_id", table_name="cdi_clinician_responses")
    op.drop_index("ix_cdi_responses_query_id", table_name="cdi_clinician_responses")
    op.drop_table("cdi_clinician_responses")

    op.drop_index("ix_cdi_queries_sla_due", table_name="cdi_provider_queries")
    op.drop_index("ix_cdi_queries_clinician", table_name="cdi_provider_queries")
    op.drop_index("ix_cdi_queries_lifecycle", table_name="cdi_provider_queries")
    op.drop_index("ix_cdi_queries_gap_id", table_name="cdi_provider_queries")
    op.drop_index("ix_cdi_queries_case_id", table_name="cdi_provider_queries")
    op.drop_table("cdi_provider_queries")

    op.drop_index("ix_cdi_gaps_status", table_name="cdi_documentation_gaps")
    op.drop_index("ix_cdi_gaps_type", table_name="cdi_documentation_gaps")
    op.drop_index("ix_cdi_gaps_case_id", table_name="cdi_documentation_gaps")
    op.drop_table("cdi_documentation_gaps")

    op.drop_index("ix_cdi_cases_created_by", table_name="cdi_cases")
    op.drop_index("ix_cdi_cases_completion", table_name="cdi_cases")
    op.drop_index("ix_cdi_cases_run_id", table_name="cdi_cases")
    op.drop_index("ix_cdi_cases_encounter", table_name="cdi_cases")
    op.drop_index("ix_cdi_cases_patient", table_name="cdi_cases")
    op.drop_index("ix_cdi_cases_org_created", table_name="cdi_cases")
    op.drop_table("cdi_cases")
