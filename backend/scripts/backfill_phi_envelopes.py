"""Dry-run-by-default revision-071 PHI envelope backfill and verifier.

Run before upgrading from 070 to 071. The migration role is used because the
operation changes stored representation; FORCE RLS is still honored by binding
one organization per transaction. No key or plaintext is written to output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

# Keep the operator command directly runnable from either the repository root
# or backend/ without requiring an editable package installation.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.phi_encryption import (
    encrypt_phi_v1,
    is_encrypted_value,
    is_legacy_v1_enabled,
)


TEXT_COLUMNS = {
    "clinical_facts": ("encrypted_text", "encrypted_evidence_json"),
    "guided_documents": (
        "encrypted_string_document_json", "encrypted_structured_document_json",
        "encrypted_labels_json", "encrypted_classic_sections_json",
    ),
    "guided_sections": ("encrypted_definition_json",),
    "encounters": ("admission_reason", "discharge_summary"),
    "documents": ("content",),
    "clinical_evidences": ("text",),
    "code_candidates": ("finding", "human_reason"),
    "coding_review_runs": ("reason", "encounter_text", "encounter_text_redacted"),
    "coding_reviews": ("report_markdown", "report_html", "reviewer_notes", "error_message"),
    "cdi_documentation_gaps": (
        "description", "why_it_matters", "minimal_clarification_needed", "evidence_quote",
    ),
    "cdi_provider_queries": ("topic", "reason", "query_text", "evidence_quote"),
    "cdi_clinician_responses": ("selected_option", "free_text_response"),
}
JSON_COLUMNS = {
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
        "high_risk_coding_points", "evidence_chain", "risk_route", "safety_gate",
        "drg_route", "pipeline_stages_observed", "pipeline_stage_meta",
        "human_review_records",
    ),
    "coding_reviews": (
        "primary_diagnosis_evidence_ids", "primary_diagnosis_reasoning",
        "main_procedure_evidence_ids", "secondary_diagnoses", "other_procedures",
        "diagnosis_analysis", "procedure_analysis", "documentation_gaps",
        "uncodable_items", "drg_impact", "human_checklist", "validation_summary",
        "evidence_ranking", "confidence_calibration",
    ),
}


def _url(value: str) -> str:
    for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
        value = value.replace(driver, "", 1)
    if not value.startswith(("postgresql://", "postgres://")):
        raise ValueError("revision-071 backfill requires PostgreSQL")
    return value


@dataclass
class Counts:
    scanned: int = 0
    plaintext: int = 0
    encrypted: int = 0
    updated: int = 0


def _serialize_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def run(database_url: str, *, execute: bool) -> dict[str, Any]:
    if not is_legacy_v1_enabled():
        raise RuntimeError("legacy v1 PHI encryption key must be configured")
    report: dict[str, Counts] = {}
    with psycopg.connect(_url(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM organizations ORDER BY id")
            organizations = [row[0] for row in cursor.fetchall()]

        for organization_id in organizations:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('icoder.current_organization_id', %s, true)",
                        (organization_id,),
                    )
                    for is_json, mapping in ((False, TEXT_COLUMNS), (True, JSON_COLUMNS)):
                        for table, columns in mapping.items():
                            key_columns = ["id"]
                            query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
                                sql.SQL(", ").join(map(sql.Identifier, key_columns + list(columns))),
                                sql.Identifier(table), sql.Identifier("id"),
                            )
                            cursor.execute(query)
                            for row in cursor.fetchall():
                                row_id, values = row[0], row[1:]
                                for column, value in zip(columns, values):
                                    if value is None or value == "":
                                        continue
                                    report_key = f"{table}.{column}"
                                    counts = report.setdefault(report_key, Counts())
                                    counts.scanned += 1
                                    serialized = (
                                        value
                                        if is_json and isinstance(value, str)
                                        and is_encrypted_value(value)
                                        else (_serialize_json(value) if is_json else str(value))
                                    )
                                    if is_encrypted_value(serialized):
                                        counts.encrypted += 1
                                        continue
                                    counts.plaintext += 1
                                    if execute:
                                        encrypted = encrypt_phi_v1(serialized)
                                        stored: Any = Jsonb(encrypted) if is_json else encrypted
                                        cursor.execute(
                                            sql.SQL("UPDATE {} SET {}=%s WHERE id=%s").format(
                                                sql.Identifier(table), sql.Identifier(column),
                                            ),
                                            (stored, row_id),
                                        )
                                        counts.updated += 1
    total_plaintext = sum(item.plaintext for item in report.values())
    total_updated = sum(item.updated for item in report.values())
    return {
        "schema_version": "icoder.phi-envelope-backfill/v1",
        "mode": "execute" if execute else "dry_run",
        "organizations_scanned": len(organizations),
        "plaintext_values": total_plaintext,
        "updated_values": total_updated,
        "columns": {
            key: vars(value) for key, value in sorted(report.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("P1_POSTGRES_MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("P1_POSTGRES_MIGRATION_DATABASE_URL is required")
    print(json.dumps(run(database_url, execute=args.execute), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
