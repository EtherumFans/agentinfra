# iCoDer Backend - Database Setup
import logging
import sqlite3
from datetime import datetime
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

logger = logging.getLogger(__name__)

# Production schema changes are applied exclusively through Alembic.  Keeping
# the expected revision explicit makes an application image fail closed when
# it is started before (or against a database behind) its migration job.
PRODUCTION_SCHEMA_REVISION = "077"
TENANT_POLICY_NAME = "icoder_tenant_isolation"
PROTECTED_TENANT_TABLES = (
    "patient_contexts",
    "run_trace_events",
    "run_history",
    "transactions",
    "contexts",
    "memory_consents",
    "conversation_memories",
    "context_messages",
    "context_task_refs",
    "context_artifact_refs",
    "original_input_audit",
    "a2a_task_executions",
    "a2a_task_events",
    "a2a_task_artifacts",
    "a2a_artifact_objects",
    "a2a_artifact_download_grants",
    "stt_interactions",
    "stt_recordings",
    "stt_transcripts",
    "stt_stream_leases",
    "stt_stream_checkpoints",
    "stt_stream_checkpoint_chunks",
    "agent_connectors",
    "connector_credentials",
    "connector_execution_audit",
    "api_keys",
    "oauth_clients",
    "oauth_tokens",
    "organization_invite_deliveries",
    "organization_invites",
    "organization_members",
    "team_invites",
    "team_members",
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
SPLIT_POLICY_TENANT_TABLES = ("audit_logs",)
IMMUTABLE_AUDIT_ARCHIVE_TABLE = "audit_integrity_archive"
PHI_ENVELOPE_CONSTRAINT_COUNT = 71

_is_sqlite = "sqlite" in settings.DATABASE_URL

# SQL echo used to follow the broad DEBUG switch.  In local Compose this wrote
# bound parameters, including complete clinical notes, to stdout.  Statement
# logging is now an explicit local diagnostic switch and parameters remain
# hidden even when another logger enables sqlalchemy.engine at INFO level.
_engine_kwargs: dict = {
    "echo": settings.ICODER_DATABASE_SQL_ECHO,
    "hide_parameters": True,
}
if _is_sqlite:
    # Python 3.12 deprecated sqlite3's implicit datetime adapter. Register an
    # explicit ISO-8601 adapter for local/test SQLite so timestamp persistence
    # remains deterministic across Python upgrades. SQLAlchemy continues to
    # own result conversion for its DateTime columns.
    sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
    # Local development and offline E2E can issue several Agent runs at once.
    # SQLite's default rollback journal + 5s busy timeout turns ordinary
    # concurrent run_history/audit writes into ``database is locked`` errors.
    # WAL permits readers alongside the single writer, while the longer busy
    # timeout lets short write transactions serialize instead of failing.
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30,
    }
else:
    # Synchronous A2A adapters execute bounded async database work on worker
    # thread event loops. asyncpg pooled connections are loop-affine, so they
    # must not be reused by those short-lived loops.
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

logger.info(f"Database: {'SQLite' if _is_sqlite else 'PostgreSQL'}")
if not _is_sqlite:
    logger.info("PostgreSQL connections: NullPool (cross-event-loop safe)")


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Export as factory for background tasks that need their own sessions
async_session_factory = AsyncSessionLocal


async def init_db():
    """Initialize local/test tables from ORM metadata.

    Cloud startup never calls this function. Production schema ownership is
    Alembic-only and is verified by :func:`verify_production_database`.
    """
    # Import the model package before reading ``Base.metadata``.  Test modules
    # may call ``init_db`` before a feature router imports its model (for
    # example the Streams checkpoint tables), which otherwise makes schema
    # creation depend on test collection/import order.
    from app import models as _models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def verify_production_database() -> None:
    """Verify that cloud runtime is attached to the governed PostgreSQL schema.

    The application role must not be a PostgreSQL superuser or carry
    ``BYPASSRLS``; either capability would silently defeat FORCE RLS.  Every
    protected table must have RLS enabled and forced before the API accepts
    traffic.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError("cloud runtime requires PostgreSQL as authoritative storage")

    async with engine.connect() as connection:
        revision = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
        if revision != PRODUCTION_SCHEMA_REVISION:
            raise RuntimeError(
                "database schema is not at the production revision: "
                f"expected {PRODUCTION_SCHEMA_REVISION}, found {revision!r}"
            )

        role = (
            await connection.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one_or_none()
        if role is None or bool(role.rolsuper) or bool(role.rolbypassrls):
            raise RuntimeError(
                "application database role must exist and must not have "
                "SUPERUSER or BYPASSRLS"
            )

        rows = await connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "a.attnotnull "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "AND a.attname = 'organization_id' AND NOT a.attisdropped "
                "WHERE n.nspname = current_schema() "
                "AND c.relname = ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(PROTECTED_TENANT_TABLES)},
        )
        state = {
            row.relname: (
                bool(row.relrowsecurity),
                bool(row.relforcerowsecurity),
                bool(row.attnotnull),
            )
            for row in rows
        }
        invalid = [
            table for table in PROTECTED_TENANT_TABLES
            if state.get(table) != (True, True, True)
        ]
        if invalid:
            raise RuntimeError(
                "tenant RLS/NOT NULL enforcement is incomplete for: "
                + ", ".join(invalid)
            )

        policy_rows = await connection.execute(
            text(
                "SELECT tablename FROM pg_policies "
                "WHERE schemaname = current_schema() "
                "AND policyname = :policy_name AND cmd = 'ALL' "
                "AND qual IS NOT NULL AND with_check IS NOT NULL"
            ),
            {"policy_name": TENANT_POLICY_NAME},
        )
        policy_tables = set(policy_rows.scalars())
        missing_policies = sorted(set(PROTECTED_TENANT_TABLES) - policy_tables)
        if missing_policies:
            raise RuntimeError(
                "tenant RLS policy is missing or incomplete for: "
                + ", ".join(missing_policies)
            )

        split_rows = await connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=current_schema() "
                "AND c.relname = ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(SPLIT_POLICY_TENANT_TABLES)},
        )
        split_state = {
            row.relname: (bool(row.relrowsecurity), bool(row.relforcerowsecurity))
            for row in split_rows
        }
        invalid_split = [
            table for table in SPLIT_POLICY_TENANT_TABLES
            if split_state.get(table) != (True, True)
        ]
        if invalid_split:
            raise RuntimeError(
                "split-policy tenant RLS enforcement is incomplete for: "
                + ", ".join(invalid_split)
            )
        missing_split_policies = sorted(
            set(SPLIT_POLICY_TENANT_TABLES) - policy_tables
        )
        if missing_split_policies:
            raise RuntimeError(
                "split-policy tenant isolation policy is missing for: "
                + ", ".join(missing_split_policies)
            )

        if settings.ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED:
            archive_gate = (
                await connection.execute(
                    text(
                        "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                        "EXISTS (SELECT 1 FROM pg_policies p WHERE "
                        "p.schemaname=current_schema() AND p.tablename=c.relname "
                        "AND p.policyname='icoder_audit_archive_tenant_read' "
                        "AND p.cmd='SELECT' AND p.qual IS NOT NULL), "
                        "EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid=c.oid "
                        "AND t.tgname='trg_audit_archive_immutable' "
                        "AND NOT t.tgisinternal) "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname=current_schema() AND c.relname=:table"
                    ),
                    {"table": IMMUTABLE_AUDIT_ARCHIVE_TABLE},
                )
            ).one_or_none()
            if archive_gate is None or tuple(bool(value) for value in archive_gate) != (
                True, True, True, True,
            ):
                raise RuntimeError(
                    "audit integrity archive RLS/immutability enforcement is incomplete"
                )

            # Advanced mode resolves the signer before accepting traffic so a
            # missing key cannot be deferred until the first audit event.
            from app.services.audit_integrity import configured_audit_signer
            configured_audit_signer()

        phi_gate = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM pg_constraint con "
                    "JOIN pg_class c ON c.oid=con.conrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=current_schema() AND con.contype='c' "
                    "AND con.conname LIKE 'ck_phi_envelope_%'"
                )
            )
        ).scalar_one()
        if int(phi_gate) != PHI_ENVELOPE_CONSTRAINT_COUNT:
            raise RuntimeError(
                "PHI envelope plaintext-clearance constraints are incomplete: "
                f"expected {PHI_ENVELOPE_CONSTRAINT_COUNT}, found {phi_gate}"
            )
        from app.services.phi_encryption import is_encryption_enabled
        if not is_encryption_enabled():
            raise RuntimeError(
                "PostgreSQL production runtime requires PHI envelope encryption"
            )



def run_migrations():
    """Run Alembic migrations from the command line.

    Usage: python -m app.database migrate
    """
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        run_migrations()
