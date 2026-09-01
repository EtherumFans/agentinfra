"""Enforce tenant isolation for Wave 5 PHI clinical data.

Revision ID: 069
Revises: 068
Create Date: 2026-09-01

The migration derives missing tenant ownership only through an authoritative
parent edge.  Ambiguous, orphaned, or conflicting rows abort the migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "agent_task_feedback",
    "cdi_cases",
    "cdi_clinician_responses",
    "cdi_document_versions",
    "cdi_documentation_gaps",
    "cdi_notification_subscriptions",
    "cdi_provider_queries",
    "clinical_evidences",
    "clinical_facts",
    "code_candidates",
    "coding_review_runs",
    "coding_reviews",
    "documents",
    "encounters",
    "feedback_training_authorizations",
    "guided_documents",
    "guided_sections",
)
NEW_TENANT_COLUMNS = (
    "cdi_documentation_gaps",
    "cdi_provider_queries",
    "cdi_clinician_responses",
    "cdi_document_versions",
)
LEGACY_NULLABLE_TABLES = (
    "coding_reviews",
    "clinical_evidences",
    "code_candidates",
    "coding_review_runs",
)
WIDE_TENANT_TABLES = ("clinical_facts", "guided_documents", "guided_sections")
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


def _count(statement: str) -> int:
    return int(op.get_bind().exec_driver_sql(statement).scalar_one())


def _backfill_and_validate() -> None:
    # Only deterministic parent ownership is permitted as migration evidence.
    op.execute(
        "UPDATE cdi_documentation_gaps child SET organization_id=parent.organization_id "
        "FROM cdi_cases parent WHERE child.case_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE cdi_provider_queries child SET organization_id=parent.organization_id "
        "FROM cdi_cases parent WHERE child.case_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE cdi_clinician_responses child SET organization_id=parent.organization_id "
        "FROM cdi_cases parent WHERE child.case_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE cdi_document_versions child SET organization_id=parent.organization_id "
        "FROM cdi_cases parent WHERE child.case_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE coding_reviews child SET organization_id=parent.organization_id "
        "FROM encounters parent WHERE child.encounter_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE clinical_evidences child SET organization_id=parent.organization_id "
        "FROM coding_reviews parent WHERE child.review_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE code_candidates child SET organization_id=parent.organization_id "
        "FROM coding_reviews parent WHERE child.review_id=parent.id "
        "AND child.organization_id IS NULL"
    )
    op.execute(
        "UPDATE coding_review_runs child SET organization_id=evidence.organization_id "
        "FROM (SELECT trace_id, min(organization_id) AS organization_id "
        "FROM run_history WHERE trace_id IS NOT NULL "
        "GROUP BY trace_id HAVING count(DISTINCT organization_id)=1) evidence "
        "WHERE child.trace_id=evidence.trace_id AND child.organization_id IS NULL"
    )

    checks = {
        f"{table}:null_tenant": (
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        )
        for table in TENANT_TABLES
    }
    checks.update(
        {
            "cdi_gaps:case_scope_mismatch": (
                "SELECT count(*) FROM cdi_documentation_gaps c JOIN cdi_cases p "
                "ON p.id=c.case_id WHERE c.organization_id<>p.organization_id"
            ),
            "cdi_queries:case_or_gap_scope_mismatch": (
                "SELECT count(*) FROM cdi_provider_queries q JOIN cdi_cases c "
                "ON c.id=q.case_id JOIN cdi_documentation_gaps g ON g.id=q.gap_id "
                "WHERE q.organization_id<>c.organization_id OR "
                "q.organization_id<>g.organization_id OR q.case_id<>g.case_id"
            ),
            "cdi_responses:case_or_query_scope_mismatch": (
                "SELECT count(*) FROM cdi_clinician_responses r JOIN cdi_cases c "
                "ON c.id=r.case_id JOIN cdi_provider_queries q ON q.id=r.query_id "
                "WHERE r.organization_id<>c.organization_id OR "
                "r.organization_id<>q.organization_id OR r.case_id<>q.case_id"
            ),
            "cdi_versions:case_or_query_scope_mismatch": (
                "SELECT count(*) FROM cdi_document_versions v JOIN cdi_cases c "
                "ON c.id=v.case_id LEFT JOIN cdi_provider_queries q ON q.id=v.query_id "
                "WHERE v.organization_id<>c.organization_id OR "
                "(v.query_id IS NOT NULL AND (q.id IS NULL OR "
                "v.organization_id<>q.organization_id OR v.case_id<>q.case_id))"
            ),
            "coding_reviews:encounter_scope_mismatch": (
                "SELECT count(*) FROM coding_reviews r JOIN encounters e "
                "ON e.id=r.encounter_id WHERE r.organization_id<>e.organization_id"
            ),
            "clinical_evidences:parent_scope_mismatch": (
                "SELECT count(*) FROM clinical_evidences e JOIN coding_reviews r "
                "ON r.id=e.review_id JOIN documents d ON d.id=e.doc_id WHERE "
                "e.organization_id<>r.organization_id OR "
                "e.organization_id<>d.organization_id OR "
                "r.encounter_id<>d.encounter_id"
            ),
            "code_candidates:review_scope_mismatch": (
                "SELECT count(*) FROM code_candidates c JOIN coding_reviews r "
                "ON r.id=c.review_id WHERE c.organization_id<>r.organization_id"
            ),
            "documents:encounter_scope_mismatch": (
                "SELECT count(*) FROM documents d JOIN encounters e "
                "ON e.id=d.encounter_id WHERE d.organization_id<>e.organization_id"
            ),
            "agent_feedback:context_scope_mismatch": (
                "SELECT count(*) FROM agent_task_feedback f JOIN contexts c "
                "ON c.id=f.context_id WHERE f.organization_id<>c.organization_id"
            ),
            "feedback_authorizations:feedback_scope_mismatch": (
                "SELECT count(*) FROM feedback_training_authorizations a "
                "JOIN agent_task_feedback f ON f.id=a.feedback_id WHERE "
                "a.organization_id<>f.organization_id OR a.context_id<>f.context_id "
                "OR a.task_id<>f.task_id"
            ),
            "coding_review_runs:trace_scope_mismatch": (
                "SELECT count(*) FROM coding_review_runs child JOIN "
                "(SELECT trace_id, min(organization_id) AS organization_id "
                "FROM run_history WHERE trace_id IS NOT NULL GROUP BY trace_id "
                "HAVING count(DISTINCT organization_id)=1) evidence "
                "ON evidence.trace_id=child.trace_id WHERE "
                "child.organization_id<>evidence.organization_id"
            ),
        }
    )
    for table in WIDE_TENANT_TABLES:
        checks[f"{table}:tenant_id_too_long"] = (
            f'SELECT count(*) FROM "{table}" WHERE length(organization_id)>12'
        )
    invalid: dict[str, int] = {}
    for key, sql in checks.items():
        count = _count(sql)
        if count:
            invalid[key] = count
    if invalid:
        details = ", ".join(f"{k}={v}" for k, v in sorted(invalid.items()))
        raise RuntimeError(
            "migration 069 requires evidence-backed PHI clinical tenant "
            "reconciliation: " + details
        )


def _unique(name: str, table: str, columns: list[str]) -> None:
    op.create_unique_constraint(name, table, columns)


def _fk(
    name: str,
    source: str,
    target: str,
    local: list[str],
    remote: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    op.create_foreign_key(name, source, target, local, remote, ondelete=ondelete)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in NEW_TENANT_COLUMNS:
        op.add_column(table, sa.Column("organization_id", sa.String(12), nullable=True))
        _fk(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
        )

    _backfill_and_validate()
    for table in NEW_TENANT_COLUMNS + LEGACY_NULLABLE_TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN organization_id SET NOT NULL')
    for table in WIDE_TENANT_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id '
            "TYPE varchar(12) USING organization_id::varchar(12)"
        )
        _fk(
            f"fk_{table}_organization_id",
            table,
            "organizations",
            ["organization_id"],
            ["id"],
        )

    # Parent composite keys make tenant ownership part of referential identity.
    for name, table, columns in (
        ("uq_cdi_cases_org_id", "cdi_cases", ["organization_id", "id"]),
        ("uq_cdi_gaps_org_case_id", "cdi_documentation_gaps", ["organization_id", "case_id", "id"]),
        ("uq_cdi_queries_org_case_id", "cdi_provider_queries", ["organization_id", "case_id", "id"]),
        ("uq_encounters_org_id", "encounters", ["organization_id", "id"]),
        ("uq_documents_org_id", "documents", ["organization_id", "id"]),
        ("uq_coding_reviews_org_id", "coding_reviews", ["organization_id", "id"]),
        ("uq_agent_feedback_org_context_task_id", "agent_task_feedback", ["organization_id", "context_id", "task_id", "id"]),
    ):
        _unique(name, table, columns)

    replacements = (
        ("fk_cdi_gaps_case", "cdi_documentation_gaps", "cdi_cases", ["organization_id", "case_id"], ["organization_id", "id"], None, "fk_cdi_gaps_case_scope"),
        ("fk_cdi_queries_case", "cdi_provider_queries", "cdi_cases", ["organization_id", "case_id"], ["organization_id", "id"], None, "fk_cdi_queries_case_scope"),
        ("fk_cdi_queries_gap", "cdi_provider_queries", "cdi_documentation_gaps", ["organization_id", "case_id", "gap_id"], ["organization_id", "case_id", "id"], None, "fk_cdi_queries_gap_scope"),
        ("fk_cdi_responses_case", "cdi_clinician_responses", "cdi_cases", ["organization_id", "case_id"], ["organization_id", "id"], None, "fk_cdi_responses_case_scope"),
        ("fk_cdi_responses_query", "cdi_clinician_responses", "cdi_provider_queries", ["organization_id", "case_id", "query_id"], ["organization_id", "case_id", "id"], None, "fk_cdi_responses_query_scope"),
        ("fk_cdi_docvers_case", "cdi_document_versions", "cdi_cases", ["organization_id", "case_id"], ["organization_id", "id"], None, "fk_cdi_docvers_case_scope"),
        ("fk_cdi_docvers_query", "cdi_document_versions", "cdi_provider_queries", ["organization_id", "case_id", "query_id"], ["organization_id", "case_id", "id"], None, "fk_cdi_docvers_query_scope"),
        ("documents_encounter_id_fkey", "documents", "encounters", ["organization_id", "encounter_id"], ["organization_id", "id"], None, "fk_documents_encounter_scope"),
        ("coding_reviews_encounter_id_fkey", "coding_reviews", "encounters", ["organization_id", "encounter_id"], ["organization_id", "id"], None, "fk_coding_reviews_encounter_scope"),
        ("clinical_evidences_review_id_fkey", "clinical_evidences", "coding_reviews", ["organization_id", "review_id"], ["organization_id", "id"], None, "fk_clinical_evidences_review_scope"),
        ("clinical_evidences_doc_id_fkey", "clinical_evidences", "documents", ["organization_id", "doc_id"], ["organization_id", "id"], None, "fk_clinical_evidences_document_scope"),
        ("code_candidates_review_id_fkey", "code_candidates", "coding_reviews", ["organization_id", "review_id"], ["organization_id", "id"], None, "fk_code_candidates_review_scope"),
        ("agent_task_feedback_context_id_fkey", "agent_task_feedback", "contexts", ["organization_id", "context_id"], ["organization_id", "id"], "CASCADE", "fk_agent_feedback_context_scope"),
        ("feedback_training_authorizations_feedback_id_fkey", "feedback_training_authorizations", "agent_task_feedback", ["organization_id", "context_id", "task_id", "feedback_id"], ["organization_id", "context_id", "task_id", "id"], "CASCADE", "fk_feedback_training_feedback_scope"),
    )
    for old, source, target, local, remote, ondelete, new in replacements:
        op.drop_constraint(old, source, type_="foreignkey")
        _fk(new, source, target, local, remote, ondelete=ondelete)
    _fk(
        "fk_feedback_training_context_scope",
        "feedback_training_authorizations",
        "contexts",
        ["organization_id", "context_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )

    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON "{table}" '
            f"USING ({TENANT_EXPRESSION}) WITH CHECK ({TENANT_EXPRESSION})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_constraint(
        "fk_feedback_training_context_scope",
        "feedback_training_authorizations",
        type_="foreignkey",
    )

    replacements = (
        ("fk_feedback_training_feedback_scope", "feedback_training_authorizations", "agent_task_feedback", ["feedback_id"], ["id"], "CASCADE", "feedback_training_authorizations_feedback_id_fkey"),
        ("fk_agent_feedback_context_scope", "agent_task_feedback", "contexts", ["context_id"], ["id"], "CASCADE", "agent_task_feedback_context_id_fkey"),
        ("fk_code_candidates_review_scope", "code_candidates", "coding_reviews", ["review_id"], ["id"], None, "code_candidates_review_id_fkey"),
        ("fk_clinical_evidences_document_scope", "clinical_evidences", "documents", ["doc_id"], ["id"], None, "clinical_evidences_doc_id_fkey"),
        ("fk_clinical_evidences_review_scope", "clinical_evidences", "coding_reviews", ["review_id"], ["id"], None, "clinical_evidences_review_id_fkey"),
        ("fk_coding_reviews_encounter_scope", "coding_reviews", "encounters", ["encounter_id"], ["id"], None, "coding_reviews_encounter_id_fkey"),
        ("fk_documents_encounter_scope", "documents", "encounters", ["encounter_id"], ["id"], None, "documents_encounter_id_fkey"),
        ("fk_cdi_docvers_query_scope", "cdi_document_versions", "cdi_provider_queries", ["query_id"], ["id"], None, "fk_cdi_docvers_query"),
        ("fk_cdi_docvers_case_scope", "cdi_document_versions", "cdi_cases", ["case_id"], ["id"], None, "fk_cdi_docvers_case"),
        ("fk_cdi_responses_query_scope", "cdi_clinician_responses", "cdi_provider_queries", ["query_id"], ["id"], None, "fk_cdi_responses_query"),
        ("fk_cdi_responses_case_scope", "cdi_clinician_responses", "cdi_cases", ["case_id"], ["id"], None, "fk_cdi_responses_case"),
        ("fk_cdi_queries_gap_scope", "cdi_provider_queries", "cdi_documentation_gaps", ["gap_id"], ["id"], None, "fk_cdi_queries_gap"),
        ("fk_cdi_queries_case_scope", "cdi_provider_queries", "cdi_cases", ["case_id"], ["id"], None, "fk_cdi_queries_case"),
        ("fk_cdi_gaps_case_scope", "cdi_documentation_gaps", "cdi_cases", ["case_id"], ["id"], None, "fk_cdi_gaps_case"),
    )
    for old, source, target, local, remote, ondelete, new in replacements:
        op.drop_constraint(old, source, type_="foreignkey")
        _fk(new, source, target, local, remote, ondelete=ondelete)
    for name, table in (
        ("uq_agent_feedback_org_context_task_id", "agent_task_feedback"),
        ("uq_coding_reviews_org_id", "coding_reviews"),
        ("uq_documents_org_id", "documents"),
        ("uq_encounters_org_id", "encounters"),
        ("uq_cdi_queries_org_case_id", "cdi_provider_queries"),
        ("uq_cdi_gaps_org_case_id", "cdi_documentation_gaps"),
        ("uq_cdi_cases_org_id", "cdi_cases"),
    ):
        op.drop_constraint(name, table, type_="unique")
    for table in LEGACY_NULLABLE_TABLES:
        op.execute(f'ALTER TABLE "{table}" ALTER COLUMN organization_id DROP NOT NULL')
    for table in WIDE_TENANT_TABLES:
        op.drop_constraint(
            f"fk_{table}_organization_id", table, type_="foreignkey"
        )
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id '
            "TYPE varchar(64) USING organization_id::varchar(64)"
        )
    for table in reversed(NEW_TENANT_COLUMNS):
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
