"""Live PostgreSQL attack matrix for the P1 tenant RLS release gate.

Both URLs must target the same disposable database migrated to head.  The app
URL uses the real non-superuser runtime role; the migration URL is used only
to create and remove unprotected foreign-key fixtures.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError


APP_URL = os.getenv("P1_POSTGRES_TEST_DATABASE_URL", "")
MIGRATION_URL = os.getenv("P1_POSTGRES_MIGRATION_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not (APP_URL.startswith("postgresql") and MIGRATION_URL.startswith("postgresql")),
    reason="P1 PostgreSQL application and migration URLs are not configured",
)


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@dataclass(frozen=True)
class TenantRow:
    surface: str
    table: str
    row_a: str
    row_b: str
    insert_sql: str
    parameters: dict[str, object]


def _tenant(connection: sa.Connection, organization_id: str) -> None:
    connection.execute(
        sa.text("SELECT set_config(:name, :value, true)"),
        {"name": "icoder.current_organization_id", "value": organization_id},
    )


def _insert(
    connection: sa.Connection,
    case: TenantRow,
    organization_id: str,
    row_id: str,
    substitutions: dict[object, object],
) -> None:
    parameters = {
        key: substitutions.get(value, value) for key, value in case.parameters.items()
    }
    parameters.update(org=organization_id, row_id=row_id)
    connection.execute(sa.text(case.insert_sql), parameters)


def test_core_surfaces_fail_closed_against_cross_tenant_attacks() -> None:
    app_engine = sa.create_engine(_sync_url(APP_URL))
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"p1a_{suffix}", f"p1b_{suffix}"
    user_a, user_b = f"ua{suffix}", f"ub{suffix}"
    agent_a, agent_b = f"aa{suffix}", f"ab{suffix}"
    consent_a, consent_b = f"ca{suffix}", f"cb{suffix}"

    cases = (
        TenantRow(
            "Patient", "patient_contexts", f"pa{suffix}", f"pb{suffix}",
            "INSERT INTO patient_contexts "
            "(id, organization_id, tenant_id, source_system, patient_id, visit_type, "
            "department_id, clinician_id, document_ids, purpose_of_use, "
            "consent_legal_basis, expires_at, created_by) VALUES "
            "(:row_id, :org, :org, 'p1-test', :patient, 'outpatient', 'dept', "
            "'clinician', CAST('[]' AS json), 'treatment', 'user-consent', "
            "CURRENT_TIMESTAMP + INTERVAL '1 day', 'p1-gate')",
            {"patient": f"patient-{suffix}"},
        ),
        TenantRow(
            "Trace event", "run_trace_events", f"tea{suffix}", f"teb{suffix}",
            "INSERT INTO run_trace_events "
            "(id, run_id, organization_id, step, status, duration_ms, ts) VALUES "
            "(:row_id, :row_id, :org, 'start', 'ok', 0, 0)",
            {},
        ),
        TenantRow(
            "Trace run", "run_history", f"rha{suffix}", f"rhb{suffix}",
            "INSERT INTO run_history "
            "(id, organization_id, agent_id, run_id, input_text, output_summary) "
            "VALUES (:row_id, :org, :agent, :row_id, 'redacted-input', 'summary')",
            {"agent": agent_a},
        ),
        TenantRow(
            "Usage", "transactions", f"txa{suffix}", f"txb{suffix}",
            "INSERT INTO transactions "
            "(id, organization_id, user_id, type, amount, balance_after, description, "
            "source) VALUES (:row_id, :org, :user, 'debit', 1, 99, 'p1-gate', "
            "'p1-test')",
            {"user": user_a},
        ),
        TenantRow(
            "Context", "contexts", f"cta{suffix}", f"ctb{suffix}",
            "INSERT INTO contexts "
            "(id, organization_id, created_at, updated_at, expires_at, agent_id, "
            "status, metadata_json) VALUES (:row_id, :org, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 day', :agent, "
            "'active', '{}')",
            {"agent": agent_a},
        ),
        TenantRow(
            "Memory consent", "memory_consents", consent_a, consent_b,
            "INSERT INTO memory_consents "
            "(id, organization_id, user_id, agent_id, purpose_of_use, expires_at, "
            "created_by) VALUES (:row_id, :org, :user, :agent, 'treatment', "
            "CURRENT_TIMESTAMP + INTERVAL '1 day', 'p1-gate')",
            {"user": user_a, "agent": agent_a},
        ),
        TenantRow(
            "Memory", "conversation_memories", f"ma{suffix}", f"mb{suffix}",
            "INSERT INTO conversation_memories "
            "(id, organization_id, user_id, agent_id, session_id, role, content, "
            "importance, consent_id, actor_type, actor_id, purpose_of_use) VALUES "
            "(:row_id, :org, :user, :agent, :session, 'user', 'encrypted-test', "
            "0.5, :consent, 'user', :user, 'treatment')",
            {"user": user_a, "agent": agent_a, "session": f"session-{suffix}", "consent": consent_a},
        ),
    )

    try:
        with migration_engine.begin() as connection:
            for organization_id in (org_a, org_b):
                connection.execute(
                    sa.text(
                        "INSERT INTO organizations "
                        "(id, name, slug, plan, settings, is_active) VALUES "
                        "(:id, :id, :id, 'free', CAST('{}' AS json), true)"
                    ),
                    {"id": organization_id},
                )
            for user_id, label in ((user_a, "a"), (user_b, "b")):
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, username, email, hashed_password, "
                        "full_name, role, department, is_active, is_verified) VALUES "
                        "(:id, :username, :email, 'not-a-real-hash', 'P1 Gate', "
                        "'CODER', 'test', true, true)"
                    ),
                    {"id": user_id, "username": f"p1-{label}-{suffix}", "email": f"p1-{label}-{suffix}@invalid.example"},
                )
            for agent_id, organization_id, label in (
                (agent_a, org_a, "a"), (agent_b, org_b, "b")
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO agents (id, organization_id, name, description, "
                        "system_prompt, icon, category, expert_ids, default_expert_id, "
                        "a2a_enabled, is_prebuilt, is_published, created_by, usage_count, "
                        "aliases) VALUES (:id, :org, :name, '', '', 'Bot', 'test', "
                        "CAST('[]' AS json), '', false, false, false, 'p1-gate', 0, "
                        "CAST('[]' AS json))"
                    ),
                    {"id": agent_id, "org": organization_id, "name": f"P1 Agent {label} {suffix}"},
                )

        with app_engine.begin() as connection:
            assert connection.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            ).one() == (False, False)
            assert connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_class WHERE relname = ANY(:tables) "
                    "AND relrowsecurity AND relforcerowsecurity"
                ),
                {"tables": [case.table for case in cases]},
            ).scalar_one() == 7

        for organization_id, side, substitutions in (
            (org_a, "a", {}),
            (org_b, "b", {user_a: user_b, agent_a: agent_b, consent_a: consent_b}),
        ):
            with app_engine.begin() as connection:
                _tenant(connection, organization_id)
                for case in cases:
                    _insert(
                        connection, case, organization_id,
                        case.row_a if side == "a" else case.row_b,
                        substitutions,
                    )

        for case in cases:
            table = f'"{case.table}"'
            with app_engine.begin() as connection:
                assert connection.execute(
                    sa.text(f"SELECT count(*) FROM {table} WHERE id IN (:a, :b)"),
                    {"a": case.row_a, "b": case.row_b},
                ).scalar_one() == 0, case.surface

            with app_engine.begin() as connection:
                _tenant(connection, org_a)
                assert connection.execute(
                    sa.text(f"SELECT id FROM {table} WHERE id IN (:a, :b) ORDER BY id"),
                    {"a": case.row_a, "b": case.row_b},
                ).scalars().all() == [case.row_a], case.surface
                assert connection.execute(
                    sa.text(f"UPDATE {table} SET updated_at = updated_at WHERE id = :id"),
                    {"id": case.row_b},
                ).rowcount == 0, case.surface
                assert connection.execute(
                    sa.text(f"DELETE FROM {table} WHERE id = :id"),
                    {"id": case.row_b},
                ).rowcount == 0, case.surface

            with pytest.raises(DBAPIError, match="row-level security"):
                with app_engine.begin() as connection:
                    _tenant(connection, org_a)
                    connection.execute(
                        sa.text(
                            f"UPDATE {table} SET organization_id = :org_b WHERE id = :id"
                        ),
                        {"org_b": org_b, "id": case.row_a},
                    )
    finally:
        for organization_id, side in ((org_a, "a"), (org_b, "b")):
            try:
                with app_engine.begin() as connection:
                    _tenant(connection, organization_id)
                    for case in reversed(cases):
                        connection.execute(
                            sa.text(f'DELETE FROM "{case.table}" WHERE id = :id'),
                            {"id": case.row_a if side == "a" else case.row_b},
                        )
            except Exception:
                pass
        try:
            with migration_engine.begin() as connection:
                connection.execute(sa.text("DELETE FROM agents WHERE id IN (:a, :b)"), {"a": agent_a, "b": agent_b})
                connection.execute(sa.text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": user_a, "b": user_b})
                connection.execute(sa.text("DELETE FROM organizations WHERE id IN (:a, :b)"), {"a": org_a, "b": org_b})
        finally:
            app_engine.dispose()
            migration_engine.dispose()
