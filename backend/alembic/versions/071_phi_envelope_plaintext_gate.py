"""Enforce encrypted envelopes for Wave 5 clinical PHI columns.

Revision ID: 071
Revises: 070
Create Date: 2026-09-01

This is intentionally a gate, not a key-bearing data migration. Deployments
with legacy rows must run the controlled encryption backfill before upgrading.
Alembic never receives plaintext keys and never guesses whether a value is PHI.
"""

from __future__ import annotations

import hashlib

from alembic import op


revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


TEXT_COLUMNS: dict[str, tuple[str, ...]] = {
    # These columns were already encrypted by their repositories.  Revision
    # 071 adds the missing database-side invariant so a bypass cannot persist
    # plaintext into them.
    "clinical_facts": ("encrypted_text", "encrypted_evidence_json"),
    "guided_documents": (
        "encrypted_string_document_json",
        "encrypted_structured_document_json",
        "encrypted_labels_json",
        "encrypted_classic_sections_json",
    ),
    "guided_sections": ("encrypted_definition_json",),
    "encounters": ("admission_reason", "discharge_summary"),
    "documents": ("content",),
    "clinical_evidences": ("text",),
    "code_candidates": ("finding", "human_reason"),
    "coding_review_runs": ("reason", "encounter_text", "encounter_text_redacted"),
    "coding_reviews": ("report_markdown", "report_html", "reviewer_notes", "error_message"),
    "cdi_documentation_gaps": (
        "description", "why_it_matters", "minimal_clarification_needed",
        "evidence_quote",
    ),
    "cdi_provider_queries": ("topic", "reason", "query_text", "evidence_quote"),
    "cdi_clinician_responses": ("selected_option", "free_text_response"),
}

JSON_COLUMNS: dict[str, tuple[str, ...]] = {
    "encounters": ("existing_diagnosis_codes", "existing_procedure_codes"),
    "cdi_cases": (
        "encounter_metadata", "draft_codes", "encounter_summary",
        "coding_specificity_checklist", "risk_flags", "specialist_trace",
        "query_rewrite_queue",
    ),
    "cdi_documentation_gaps": ("candidate_codes",),
    "cdi_provider_queries": ("response_options", "evidence_spans"),
    "cdi_clinician_responses": ("response_metadata",),
    "cdi_document_versions": ("diff_summary",),
    "code_candidates": ("evidence_ids", "rule_checks"),
    "coding_review_runs": (
        "primary_diagnosis", "secondary_diagnoses", "procedures",
        "high_risk_coding_points", "evidence_chain", "risk_route",
        "safety_gate", "drg_route", "pipeline_stages_observed",
        "pipeline_stage_meta", "human_review_records",
    ),
    "coding_reviews": (
        "primary_diagnosis_evidence_ids", "primary_diagnosis_reasoning",
        "main_procedure_evidence_ids", "secondary_diagnoses",
        "other_procedures", "diagnosis_analysis", "procedure_analysis",
        "documentation_gaps", "uncodable_items", "drg_impact",
        "human_checklist", "validation_summary", "evidence_ranking",
        "confidence_calibration",
    ),
}

ENVELOPE_PATTERN = r"^v[1-9][0-9]*:gAAAAA[A-Za-z0-9_-]{90,}={0,2}$"


def _constraint_name(table: str, column: str) -> str:
    raw = f"ck_phi_envelope_{table}_{column}"
    if len(raw) <= 60:
        return raw
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()[:8]
    return f"{raw[:51]}_{digest}"


def _count(statement: str) -> int:
    return int(op.get_bind().exec_driver_sql(statement).scalar_one())


def _validate_no_plaintext() -> None:
    invalid: dict[str, int] = {}
    bind = op.get_bind()
    # Every target is FORCE-RLS tenant data.  The migration owner cannot see a
    # row until the tenant context is bound, so validate one organization at a
    # time instead of relying on owner privileges that FORCE RLS intentionally
    # removes.
    organizations = bind.exec_driver_sql(
        "SELECT id FROM organizations ORDER BY id"
    ).scalars().all()
    for organization_id in organizations:
        bind.exec_driver_sql(
            "SELECT set_config('icoder.current_organization_id', %s, true)",
            (organization_id,),
        )
        for table, columns in TEXT_COLUMNS.items():
            for column in columns:
                count = _count(
                    f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL '
                    f'AND "{column}" <> \'\' AND "{column}" !~ \'{ENVELOPE_PATTERN}\''
                )
                if count:
                    key = f"{table}.{column}"
                    invalid[key] = invalid.get(key, 0) + count
        for table, columns in JSON_COLUMNS.items():
            for column in columns:
                count = _count(
                    f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL '
                    f"AND (jsonb_typeof(\"{column}\"::jsonb) <> 'string' OR "
                    f"coalesce(\"{column}\"::jsonb #>> '{{}}', '') "
                    f"!~ '{ENVELOPE_PATTERN}')"
                )
                if count:
                    key = f"{table}.{column}"
                    invalid[key] = invalid.get(key, 0) + count
    if invalid:
        details = ", ".join(f"{key}={value}" for key, value in sorted(invalid.items()))
        raise RuntimeError(
            "migration 071 refuses plaintext PHI; run the controlled envelope "
            "backfill and verify again: " + details
        )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _validate_no_plaintext()

    # JSON payloads become opaque encrypted text. Defaults are removed because
    # PostgreSQL must never synthesize an unencrypted [] or {} value.
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP DEFAULT')
            op.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE text '
                f'USING ("{column}"::jsonb #>> \'{{}}\')'
            )

    # Bounded varchar PHI columns are widened automatically by TYPE text when
    # a check is added; Fernet overhead must never truncate a ciphertext.
    for table, columns in TEXT_COLUMNS.items():
        for column in columns:
            op.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" DROP DEFAULT')
            op.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE text '
                f'USING "{column}"::text'
            )

    for mapping in (TEXT_COLUMNS, JSON_COLUMNS):
        for table, columns in mapping.items():
            for column in columns:
                # Use driver SQL because SQLAlchemy's text parser treats the
                # literal colon in ``v1:...`` as a bind marker and silently
                # rewrites the pattern.
                op.get_bind().exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD CONSTRAINT '
                    f'"{_constraint_name(table, column)}" CHECK ('
                    f'"{column}" IS NULL OR "{column}" = \'\' OR '
                    f'"{column}" ~ \'{ENVELOPE_PATTERN}\')'
                )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for mapping in (JSON_COLUMNS, TEXT_COLUMNS):
        for table, columns in reversed(tuple(mapping.items())):
            for column in reversed(columns):
                op.execute(
                    f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS '
                    f'"{_constraint_name(table, column)}"'
                )
    for table, columns in JSON_COLUMNS.items():
        for column in columns:
            op.execute(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE json '
                f'USING to_json("{column}")'
            )
