"""Live PostgreSQL attack matrix for the P1 tenant RLS release gate.

Both URLs must target the same disposable database migrated to head.  The app
URL uses the real non-superuser runtime role; the migration URL is used only
to create and remove unprotected foreign-key fixtures.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine


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


async def _async_tenant(connection, organization_id: str) -> None:
    await connection.execute(
        sa.text("SELECT set_config(:name, :value, true)"),
        {"name": "icoder.current_organization_id", "value": organization_id},
    )


def test_tenant_table_inventory_matches_live_postgresql_schema() -> None:
    inventory_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "security"
        / "tenant_table_inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    expected = {
        row["name"]: row
        for row in inventory["tables"]
        if row["schema_presence"] != "orm_only"
    }

    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    try:
        with migration_engine.connect() as connection:
            rows = connection.execute(sa.text(
                "SELECT c.relname, a.attnotnull, c.relrowsecurity, "
                "c.relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_attribute a ON a.attrelid = c.oid "
                "AND a.attname = 'organization_id' AND NOT a.attisdropped "
                "WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            )).all()
    finally:
        migration_engine.dispose()

    actual = {
        row.relname: {
            "has_organization_id": row.attnotnull is not None,
            "organization_id_not_null": bool(row.attnotnull),
            "rls": bool(row.relrowsecurity),
            "force_rls": bool(row.relforcerowsecurity),
        }
        for row in rows
    }
    assert set(actual) == set(expected)
    assert len(actual) == inventory["database_table_count"] == 82

    for name, governed in expected.items():
        state = actual[name]
        column_state = governed["organization_id"]
        if column_state == "required":
            assert state["has_organization_id"], name
            assert state["organization_id_not_null"], name
        elif column_state == "nullable":
            assert state["has_organization_id"], name
            assert not state["organization_id_not_null"], name
        else:
            assert column_state in {"missing", "not_applicable"}
            assert not state["has_organization_id"], name

        if governed["rls"] == "force":
            assert state["rls"] and state["force_rls"], name


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


def test_context_a2a_wave_fails_closed_across_tenants() -> None:
    """Exercise the complete revision-065 ownership chain through the app role."""
    app_engine = sa.create_engine(_sync_url(APP_URL))
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"w1a_{suffix}", f"w1b_{suffix}"
    context_id, task_id = f"ctx-{suffix}", f"task-{suffix}"
    protected = (
        "context_messages", "context_task_refs", "context_artifact_refs",
        "original_input_audit", "a2a_task_executions", "a2a_task_events",
        "a2a_task_artifacts", "a2a_artifact_objects",
        "a2a_artifact_download_grants",
    )
    try:
        with migration_engine.begin() as connection:
            for organization_id in (org_a, org_b):
                connection.execute(sa.text(
                    "INSERT INTO organizations "
                    "(id, name, slug, plan, settings, is_active) VALUES "
                    "(:id, :id, :id, 'free', CAST('{}' AS json), true)"
                ), {"id": organization_id})

        with app_engine.begin() as connection:
            _tenant(connection, org_a)
            statements = (
                ("INSERT INTO contexts (id, organization_id, created_at, updated_at, "
                 "expires_at, agent_id, status, metadata_json) VALUES (:context, :org, "
                 "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL "
                 "'1 day', 'p1-agent', 'active', '{}')", {}),
                ("INSERT INTO context_messages (context_id, message_id, organization_id, "
                 "role, parts_json, timestamp) VALUES (:context, 'message-1', :org, "
                 "'user', '[]', CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO context_task_refs (context_id, task_id, organization_id, "
                 "state, started_at) VALUES (:context, :task, :org, 'submitted', "
                 "CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO context_artifact_refs (context_id, artifact_id, "
                 "organization_id, name, mime_type, url) VALUES (:context, "
                 "'artifact-ref', :org, 'artifact', 'text/plain', 'managed://test')", {}),
                ("INSERT INTO original_input_audit (id, context_id, organization_id, "
                 "original_input, created_at, retention_until) VALUES ('audit-" + suffix +
                 "', :context, :org, 'encrypted-test', CURRENT_TIMESTAMP, "
                 "CURRENT_TIMESTAMP + INTERVAL '1 day')", {}),
                ("INSERT INTO a2a_task_executions (task_id, context_id, organization_id, "
                 "agent_id, message_id, request_json, attempt_count, created_at, "
                 "updated_at) VALUES (:task, :context, :org, 'p1-agent', 'message-1', "
                 "'{}', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO a2a_task_events (task_id, context_id, organization_id, "
                 "agent_id, state, event_type, created_at) VALUES (:task, :context, "
                 ":org, 'p1-agent', 'submitted', 'submitted', CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO a2a_task_artifacts (context_id, task_id, artifact_id, "
                 "organization_id, payload_json, payload_sha256, size_bytes, created_at) "
                 "VALUES (:context, :task, 'artifact-1', :org, '{}', 'hash', 2, "
                 "CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO a2a_artifact_objects (object_id, organization_id, context_id, "
                 "task_id, artifact_id, filename_encrypted, declared_media_type, "
                 "data_classification, payload_ciphertext, payload_sha256, size_bytes, "
                 "status, malware_scan_status, dlp_scan_status, scan_engine, "
                 "scan_findings_json, actor_type, actor_id_hash, created_at) VALUES "
                 "('object-" + suffix + "', :org, :context, :task, 'artifact-1', "
                 "'encrypted-name', 'text/plain', 'deidentified', decode('00','hex'), "
                 "'hash', 1, 'quarantined', 'pending', 'clear', 'p1-test', '{}', "
                 "'service', 'actor-hash', CURRENT_TIMESTAMP)", {}),
                ("INSERT INTO a2a_artifact_download_grants (grant_id, object_id, "
                 "organization_id, actor_type, actor_id_hash, purpose_of_use, created_at, "
                 "expires_at) VALUES ('grant-" + suffix + "', 'object-" + suffix +
                 "', :org, 'service', 'actor-hash', 'treatment', CURRENT_TIMESTAMP, "
                 "CURRENT_TIMESTAMP + INTERVAL '1 day')", {}),
            )
            for statement, extra in statements:
                connection.execute(sa.text(statement), {
                    "org": org_a, "context": context_id, "task": task_id, **extra,
                })

        for organization_id, expected in (("", 0), (org_a, 1), (org_b, 0)):
            with app_engine.begin() as connection:
                if organization_id:
                    _tenant(connection, organization_id)
                for table in protected:
                    assert connection.execute(
                        sa.text(f'SELECT count(*) FROM "{table}"')
                    ).scalar_one() == expected, table

        with pytest.raises(DBAPIError, match="row-level security|foreign key"):
            with app_engine.begin() as connection:
                _tenant(connection, org_a)
                connection.execute(sa.text(
                    "INSERT INTO context_messages (context_id, message_id, "
                    "organization_id, role, parts_json, timestamp) VALUES "
                    "(:context, 'cross-tenant', :org_b, 'user', '[]', CURRENT_TIMESTAMP)"
                ), {"context": context_id, "org_b": org_b})
    finally:
        try:
            with migration_engine.begin() as connection:
                _tenant(connection, org_a)
                connection.execute(
                    sa.text("DELETE FROM original_input_audit WHERE context_id = :id"),
                    {"id": context_id},
                )
                connection.execute(
                    sa.text("DELETE FROM contexts WHERE id = :id"), {"id": context_id}
                )
                connection.execute(sa.text(
                    "DELETE FROM organizations WHERE id IN (:a, :b)"
                ), {"a": org_a, "b": org_b})
        finally:
            app_engine.dispose()
            migration_engine.dispose()


def test_stt_streams_wave_fails_closed_across_tenants() -> None:
    """Exercise all revision-066 STT/Streams tables through the app role."""
    app_engine = sa.create_engine(_sync_url(APP_URL))
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"w2a_{suffix}", f"w2b_{suffix}"
    owner_id = f"owner-{suffix}"
    interaction_id = f"interaction-{suffix}"
    recording_id = f"recording-{suffix}"
    transcript_id = f"transcript-{suffix}"
    session_id = str(uuid.uuid4())
    protected = (
        "stt_interactions",
        "stt_recordings",
        "stt_transcripts",
        "stt_stream_leases",
        "stt_stream_checkpoints",
        "stt_stream_checkpoint_chunks",
    )
    try:
        with migration_engine.begin() as connection:
            for organization_id in (org_a, org_b):
                connection.execute(sa.text(
                    "INSERT INTO organizations "
                    "(id, name, slug, plan, settings, is_active) VALUES "
                    "(:id, :id, :id, 'free', CAST('{}' AS json), true)"
                ), {"id": organization_id})

        with app_engine.begin() as connection:
            _tenant(connection, org_a)
            parameters = {
                "org": org_a,
                "owner": owner_id,
                "interaction": interaction_id,
                "recording": recording_id,
                "transcript": transcript_id,
                "session": session_id,
            }
            statements = (
                "INSERT INTO stt_interactions "
                "(organization_id, owner_id, interaction_id, created_at) VALUES "
                "(:org, :owner, :interaction, CURRENT_TIMESTAMP)",
                "INSERT INTO stt_recordings "
                "(organization_id, owner_id, interaction_id, recording_id, "
                "media_type, encrypted_content, byte_length, content_sha256, created_at) "
                "VALUES (:org, :owner, :interaction, :recording, 'audio/wav', "
                "decode('00', 'hex'), 1, 'sha256-test', CURRENT_TIMESTAMP)",
                "INSERT INTO stt_transcripts "
                "(organization_id, owner_id, interaction_id, transcript_id, "
                "recording_id, status, participant_roles_json, created_at, updated_at) "
                "VALUES (:org, :owner, :interaction, :transcript, :recording, "
                "'processing', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                "INSERT INTO stt_stream_leases "
                "(organization_id, owner_id, interaction_id, session_id, acquired_at, "
                "lease_expires_at, updated_at) VALUES (:org, :owner, :interaction, "
                ":session, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '5 minutes', "
                "CURRENT_TIMESTAMP)",
                "INSERT INTO stt_stream_checkpoints "
                "(organization_id, owner_id, interaction_id, session_id, recording_id, "
                "encrypted_state_json, state_sha256, audio_bytes, audio_chunk_count, "
                "created_at, updated_at) VALUES (:org, :owner, :interaction, :session, "
                ":recording, 'encrypted-state', 'sha256-state', 1, 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                "INSERT INTO stt_stream_checkpoint_chunks "
                "(organization_id, owner_id, interaction_id, sequence, "
                "encrypted_content, byte_length, content_sha256, created_at) VALUES "
                "(:org, :owner, :interaction, 0, decode('00', 'hex'), 1, "
                "'sha256-chunk', CURRENT_TIMESTAMP)",
            )
            for statement in statements:
                connection.execute(sa.text(statement), parameters)

        for organization_id, expected in (("", 0), (org_a, 1), (org_b, 0)):
            with app_engine.begin() as connection:
                if organization_id:
                    _tenant(connection, organization_id)
                for table in protected:
                    assert connection.execute(
                        sa.text(f'SELECT count(*) FROM "{table}"')
                    ).scalar_one() == expected, table

        with pytest.raises(DBAPIError, match="row-level security|foreign key"):
            with app_engine.begin() as connection:
                _tenant(connection, org_a)
                connection.execute(sa.text(
                    "INSERT INTO stt_interactions "
                    "(organization_id, owner_id, interaction_id, created_at) VALUES "
                    "(:org_b, :owner, 'cross-tenant', CURRENT_TIMESTAMP)"
                ), {"org_b": org_b, "owner": owner_id})
    finally:
        try:
            with migration_engine.begin() as connection:
                _tenant(connection, org_a)
                for table in (
                    "stt_stream_checkpoint_chunks",
                    "stt_stream_checkpoints",
                    "stt_stream_leases",
                    "stt_transcripts",
                    "stt_recordings",
                    "stt_interactions",
                ):
                    connection.execute(sa.text(
                        f'DELETE FROM "{table}" WHERE organization_id = :org'
                    ), {"org": org_a})
                connection.execute(sa.text(
                    "DELETE FROM organizations WHERE id IN (:a, :b)"
                ), {"a": org_a, "b": org_b})
        finally:
            app_engine.dispose()
            migration_engine.dispose()


def test_agent_connector_wave_fails_closed_across_tenants() -> None:
    """Exercise revision-067 configuration, credential, and audit ownership."""
    app_engine = sa.create_engine(_sync_url(APP_URL))
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"w3a_{suffix}", f"w3b_{suffix}"
    agent_a, agent_b = f"a3a{suffix}", f"a3b{suffix}"
    connector_id = f"c3a{suffix}"
    credential_id = f"d3a{suffix}"
    audit_id = f"e3a{suffix}"
    protected = (
        "agent_connectors",
        "connector_credentials",
        "connector_execution_audit",
    )
    try:
        with migration_engine.begin() as connection:
            for organization_id in (org_a, org_b):
                connection.execute(sa.text(
                    "INSERT INTO organizations "
                    "(id, name, slug, plan, settings, is_active) VALUES "
                    "(:id, :id, :id, 'free', CAST('{}' AS json), true)"
                ), {"id": organization_id})
            for agent_id, organization_id, label in (
                (agent_a, org_a, "a"),
                (agent_b, org_b, "b"),
            ):
                connection.execute(sa.text(
                    "INSERT INTO agents (id, organization_id, name, description, "
                    "system_prompt, icon, category, expert_ids, default_expert_id, "
                    "a2a_enabled, is_prebuilt, is_published, created_by, usage_count, "
                    "aliases) VALUES (:id, :org, :name, '', '', 'Bot', 'test', "
                    "CAST('[]' AS json), '', false, false, false, 'p1-gate', 0, "
                    "CAST('[]' AS json))"
                ), {
                    "id": agent_id,
                    "org": organization_id,
                    "name": f"Wave 3 Agent {label} {suffix}",
                })

        with app_engine.begin() as connection:
            _tenant(connection, org_a)
            connection.execute(sa.text(
                "INSERT INTO agent_connectors "
                "(id, organization_id, agent_id, type, name, description, enabled, "
                "config_json, version, created_by, created_at, updated_at) VALUES "
                "(:id, :org, :agent, 'registry', 'wave-3', '', false, "
                "CAST('{}' AS json), 1, 'p1-gate', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {"id": connector_id, "org": org_a, "agent": agent_a})
            connection.execute(sa.text(
                "INSERT INTO connector_credentials "
                "(id, organization_id, connector_id, provider, secret_ref, fingerprint, "
                "secret_type, status, version, rotated_at, created_by, created_at, "
                "updated_at) VALUES (:id, :org, :connector, 'vault', "
                "'vault://p1/connectors/wave3', 'fingerprint', 'api-key', 'active', 1, "
                "CURRENT_TIMESTAMP, 'p1-gate', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {"id": credential_id, "org": org_a, "connector": connector_id})
            connection.execute(sa.text(
                "INSERT INTO connector_execution_audit "
                "(id, organization_id, connector_id, action, actor_type, actor_id, "
                "delegated_subject_id, granted_scopes, granted_purposes, policy_decision, "
                "status, retry_count, created_at, updated_at) VALUES "
                "(:id, :org, :connector, 'lookup', 'user', 'p1-actor', NULL, "
                "CAST('[]' AS json), CAST('[\"treatment\"]' AS json), 'allow', "
                "'success', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ), {"id": audit_id, "org": org_a, "connector": connector_id})

        for organization_id, expected in (("", 0), (org_a, 1), (org_b, 0)):
            with app_engine.begin() as connection:
                if organization_id:
                    _tenant(connection, organization_id)
                for table in protected:
                    assert connection.execute(
                        sa.text(f'SELECT count(*) FROM "{table}"')
                    ).scalar_one() == expected, table

        with pytest.raises(DBAPIError, match="row-level security"):
            with app_engine.begin() as connection:
                _tenant(connection, org_a)
                connection.execute(sa.text(
                    "INSERT INTO agent_connectors "
                    "(id, organization_id, agent_id, type, name, description, enabled, "
                    "config_json, version, created_by, created_at, updated_at) VALUES "
                    "('cross-rls', :org_b, :agent_b, 'registry', 'cross-rls', '', "
                    "false, CAST('{}' AS json), 1, 'p1-gate', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)"
                ), {"org_b": org_b, "agent_b": agent_b})

        with pytest.raises(DBAPIError, match="foreign key"):
            with app_engine.begin() as connection:
                _tenant(connection, org_b)
                connection.execute(sa.text(
                    "INSERT INTO agent_connectors "
                    "(id, organization_id, agent_id, type, name, description, enabled, "
                    "config_json, version, created_by, created_at, updated_at) VALUES "
                    "('cross-fk', :org_b, :agent_a, 'registry', 'cross-fk', '', "
                    "false, CAST('{}' AS json), 1, 'p1-gate', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)"
                ), {"org_b": org_b, "agent_a": agent_a})
    finally:
        try:
            with migration_engine.begin() as connection:
                _tenant(connection, org_a)
                for table in (
                    "connector_execution_audit",
                    "connector_credentials",
                    "agent_connectors",
                ):
                    connection.execute(sa.text(
                        f'DELETE FROM "{table}" WHERE organization_id = :org'
                    ), {"org": org_a})
                connection.execute(sa.text(
                    "DELETE FROM agents WHERE id IN (:a, :b)"
                ), {"a": agent_a, "b": agent_b})
                connection.execute(sa.text(
                    "DELETE FROM organizations WHERE id IN (:a, :b)"
                ), {"a": org_a, "b": org_b})
        finally:
            app_engine.dispose()
            migration_engine.dispose()


def test_transaction_local_tenant_does_not_leak_on_pool_reuse() -> None:
    """Reuse one physical backend connection across A → empty → B."""
    app_engine = sa.create_engine(
        _sync_url(APP_URL), pool_size=1, max_overflow=0, pool_pre_ping=True
    )
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"p2a_{suffix}", f"p2b_{suffix}"
    event_a, event_b = f"p2ea{suffix}", f"p2eb{suffix}"
    pids: list[int] = []
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

        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            with app_engine.begin() as connection:
                _tenant(connection, organization_id)
                connection.execute(
                    sa.text(
                        "INSERT INTO run_trace_events "
                        "(id, run_id, organization_id, step, status, duration_ms, ts) "
                        "VALUES (:id, :id, :org, 'start', 'ok', 0, 0)"
                    ),
                    {"id": event_id, "org": organization_id},
                )

        with app_engine.begin() as connection:
            _tenant(connection, org_a)
            pids.append(connection.execute(sa.text("SELECT pg_backend_pid() ")).scalar_one())
            assert connection.execute(
                sa.text("SELECT id FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            ).scalars().all() == [event_a]

        # The same checked-in physical connection must carry no tenant after
        # commit, before another request establishes its authority.
        with app_engine.begin() as connection:
            pids.append(connection.execute(sa.text("SELECT pg_backend_pid() ")).scalar_one())
            setting = connection.execute(
                sa.text(
                    "SELECT current_setting('icoder.current_organization_id', true)"
                )
            ).scalar_one_or_none()
            assert setting in (None, "")
            assert connection.execute(
                sa.text("SELECT count(*) FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            ).scalar_one() == 0

        with app_engine.begin() as connection:
            _tenant(connection, org_b)
            pids.append(connection.execute(sa.text("SELECT pg_backend_pid() ")).scalar_one())
            assert connection.execute(
                sa.text("SELECT id FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            ).scalars().all() == [event_b]

        # Prove this was connection reuse, not isolation obtained by opening
        # a different server session for each phase.
        assert len(set(pids)) == 1
    finally:
        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            try:
                with app_engine.begin() as connection:
                    _tenant(connection, organization_id)
                    connection.execute(
                        sa.text("DELETE FROM run_trace_events WHERE id = :id"),
                        {"id": event_id},
                    )
            except Exception:
                pass
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    sa.text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                    {"a": org_a, "b": org_b},
                )
        finally:
            app_engine.dispose()
            migration_engine.dispose()


@pytest.mark.asyncio
async def test_async_application_pool_reuse_clears_tenant_context() -> None:
    """Exercise the same invariant through the API runtime's async pool."""
    app_engine = create_async_engine(
        APP_URL, pool_size=1, max_overflow=0, pool_pre_ping=True
    )
    migration_engine = sa.create_engine(_sync_url(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"p3a_{suffix}", f"p3b_{suffix}"
    event_a, event_b = f"p3ea{suffix}", f"p3eb{suffix}"
    pids: list[int] = []
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
        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            async with app_engine.begin() as connection:
                await _async_tenant(connection, organization_id)
                await connection.execute(
                    sa.text(
                        "INSERT INTO run_trace_events "
                        "(id, run_id, organization_id, step, status, duration_ms, ts) "
                        "VALUES (:id, :id, :org, 'start', 'ok', 0, 0)"
                    ),
                    {"id": event_id, "org": organization_id},
                )

        async with app_engine.begin() as connection:
            await _async_tenant(connection, org_a)
            pids.append((await connection.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one())
            assert (await connection.execute(
                sa.text("SELECT id FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            )).scalars().all() == [event_a]
        async with app_engine.begin() as connection:
            pids.append((await connection.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one())
            setting = (await connection.execute(sa.text(
                "SELECT current_setting('icoder.current_organization_id', true)"
            ))).scalar_one_or_none()
            assert setting in (None, "")
            assert (await connection.execute(
                sa.text("SELECT count(*) FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            )).scalar_one() == 0
        async with app_engine.begin() as connection:
            await _async_tenant(connection, org_b)
            pids.append((await connection.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one())
            assert (await connection.execute(
                sa.text("SELECT id FROM run_trace_events WHERE id IN (:a, :b)"),
                {"a": event_a, "b": event_b},
            )).scalars().all() == [event_b]
        assert len(set(pids)) == 1
    finally:
        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            try:
                async with app_engine.begin() as connection:
                    await _async_tenant(connection, organization_id)
                    await connection.execute(
                        sa.text("DELETE FROM run_trace_events WHERE id = :id"),
                        {"id": event_id},
                    )
            except Exception:
                pass
        await app_engine.dispose()
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    sa.text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                    {"a": org_a, "b": org_b},
                )
        finally:
            migration_engine.dispose()
