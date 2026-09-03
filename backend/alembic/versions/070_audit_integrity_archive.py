"""Add cryptographically chained, append-only audit archive.

Revision ID: 070
Revises: 069
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_integrity_archive",
        sa.Column("audit_log_id", sa.String(12), nullable=False),
        sa.Column("organization_id", sa.String(12), nullable=True),
        sa.Column("stream_id", sa.String(64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("chain_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signing_algorithm", sa.String(32), nullable=False),
        sa.Column("signing_key_id", sa.String(128), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_log_id", name="uq_audit_archive_audit_log"),
        sa.UniqueConstraint("stream_id", "sequence", name="uq_audit_archive_stream_sequence"),
    )
    op.create_index("ix_audit_integrity_archive_organization_id", "audit_integrity_archive", ["organization_id"])
    op.create_index("ix_audit_integrity_archive_stream_id", "audit_integrity_archive", ["stream_id"])
    op.create_index("ix_audit_integrity_archive_chain_hash", "audit_integrity_archive", ["chain_hash"])

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE audit_integrity_archive ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_integrity_archive FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY icoder_audit_archive_tenant_read ON audit_integrity_archive "
        "FOR SELECT USING (organization_id = NULLIF("
        "current_setting('icoder.current_organization_id', true), ''))"
    )
    owner = (
        "current_user = pg_get_userbyid((SELECT relowner FROM pg_class "
        "WHERE oid = 'public.audit_integrity_archive'::regclass))"
    )
    op.execute(
        "CREATE POLICY icoder_audit_archive_owner ON audit_integrity_archive "
        f"USING ({owner}) WITH CHECK ({owner})"
    )
    audit_owner = (
        "current_user = pg_get_userbyid((SELECT relowner FROM pg_class "
        "WHERE oid = 'public.audit_logs'::regclass))"
    )
    op.execute(
        "CREATE POLICY icoder_audit_archive_source_read ON audit_logs "
        f"FOR SELECT USING ({audit_owner})"
    )
    op.execute(
        """
        CREATE FUNCTION icoder_reject_audit_archive_mutation()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$ BEGIN
          RAISE EXCEPTION 'audit integrity archive is append-only';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_audit_archive_immutable BEFORE UPDATE OR DELETE "
        "ON audit_integrity_archive FOR EACH ROW "
        "EXECUTE FUNCTION icoder_reject_audit_archive_mutation()"
    )
    op.execute(
        """
        CREATE FUNCTION icoder_audit_archive_head(p_organization_id text)
        RETURNS TABLE(sequence bigint, chain_hash text)
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE expected_org text;
        BEGIN
          expected_org := nullif(current_setting('icoder.current_organization_id', true), '');
          IF p_organization_id IS NOT NULL AND expected_org IS DISTINCT FROM p_organization_id THEN
            RAISE EXCEPTION 'audit archive tenant context mismatch';
          END IF;
          RETURN QUERY
          SELECT coalesce(a.sequence, 0), coalesce(a.chain_hash, repeat('0', 64))::text
          FROM (VALUES (1)) seed(n)
          LEFT JOIN LATERAL (
            SELECT x.sequence, x.chain_hash FROM public.audit_integrity_archive x
            WHERE x.stream_id = coalesce(p_organization_id, 'system')
            ORDER BY x.sequence DESC LIMIT 1
          ) a ON true;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION icoder_append_audit_archive(p_record jsonb)
        RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          record_org text := nullif(p_record->>'organization_id', '');
          expected_org text;
          expected_stream text := coalesce(record_org, 'system');
          head_sequence bigint;
          head_hash text;
        BEGIN
          IF coalesce(p_record->>'id', '') = '' OR coalesce(p_record->>'audit_log_id', '') = '' THEN
            RAISE EXCEPTION 'invalid audit archive record';
          END IF;
          expected_org := nullif(current_setting('icoder.current_organization_id', true), '');
          IF record_org IS NOT NULL AND expected_org IS DISTINCT FROM record_org THEN
            RAISE EXCEPTION 'audit archive tenant context mismatch';
          END IF;
          IF p_record->>'stream_id' IS DISTINCT FROM expected_stream THEN
            RAISE EXCEPTION 'audit archive stream mismatch';
          END IF;
          IF (p_record->>'payload_hash') !~ '^[0-9a-f]{64}$'
             OR (p_record->>'previous_hash') !~ '^[0-9a-f]{64}$'
             OR (p_record->>'chain_hash') !~ '^[0-9a-f]{64}$'
             OR coalesce(p_record->>'signature', '') = ''
             OR coalesce(p_record->>'signing_key_id', '') = '' THEN
            RAISE EXCEPTION 'invalid audit archive cryptographic fields';
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM public.audit_logs l
            WHERE l.id = p_record->>'audit_log_id'
              AND l.organization_id IS NOT DISTINCT FROM record_org
              AND (record_org IS NOT NULL OR l.tenancy_classification = 'MODERN_SYSTEM')
          ) THEN
            RAISE EXCEPTION 'audit archive source does not exist or tenant mismatches';
          END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended(expected_stream, 0));
          SELECT coalesce(max(a.sequence), 0) INTO head_sequence
          FROM public.audit_integrity_archive a WHERE a.stream_id = expected_stream;
          SELECT coalesce((SELECT a.chain_hash FROM public.audit_integrity_archive a
            WHERE a.stream_id = expected_stream ORDER BY a.sequence DESC LIMIT 1), repeat('0', 64))
            INTO head_hash;
          IF (p_record->>'sequence')::bigint <> head_sequence + 1
             OR p_record->>'previous_hash' IS DISTINCT FROM head_hash THEN
            RAISE EXCEPTION 'audit archive chain head changed';
          END IF;
          INSERT INTO public.audit_integrity_archive (
            id, audit_log_id, organization_id, stream_id, sequence, payload,
            payload_hash, previous_hash, chain_hash, signature,
            signing_algorithm, signing_key_id, archived_at, created_at, updated_at
          ) VALUES (
            left(p_record->>'id', 12), left(p_record->>'audit_log_id', 12), record_org,
            expected_stream, (p_record->>'sequence')::bigint, p_record->'payload',
            p_record->>'payload_hash', p_record->>'previous_hash', p_record->>'chain_hash',
            p_record->>'signature', p_record->>'signing_algorithm',
            left(p_record->>'signing_key_id', 128), (p_record->>'archived_at')::timestamptz,
            clock_timestamp(), clock_timestamp()
          );
        END $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS icoder_append_audit_archive(jsonb)")
        op.execute("DROP FUNCTION IF EXISTS icoder_audit_archive_head(text)")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_archive_immutable ON audit_integrity_archive")
        op.execute("DROP FUNCTION IF EXISTS icoder_reject_audit_archive_mutation()")
        op.execute("DROP POLICY IF EXISTS icoder_audit_archive_source_read ON audit_logs")
        op.execute("DROP POLICY IF EXISTS icoder_audit_archive_owner ON audit_integrity_archive")
        op.execute("DROP POLICY IF EXISTS icoder_audit_archive_tenant_read ON audit_integrity_archive")
    op.drop_index("ix_audit_integrity_archive_chain_hash", table_name="audit_integrity_archive")
    op.drop_index("ix_audit_integrity_archive_stream_id", table_name="audit_integrity_archive")
    op.drop_index("ix_audit_integrity_archive_organization_id", table_name="audit_integrity_archive")
    op.drop_table("audit_integrity_archive")
