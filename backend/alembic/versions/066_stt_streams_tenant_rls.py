"""Enforce PostgreSQL tenant isolation for STT and Streams state.

Revision ID: 066
Revises: 065
Create Date: 2026-09-01
"""

from alembic import op


revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "stt_interactions",
    "stt_recordings",
    "stt_transcripts",
    "stt_stream_leases",
    "stt_stream_checkpoints",
    "stt_stream_checkpoint_chunks",
)
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


def _validate_ownership() -> None:
    bind = op.get_bind()
    invalid: dict[str, int] = {}
    for table in TENANT_TABLES:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        ).scalar_one()
        if count:
            invalid[f"{table}:null_tenant"] = int(count)

    orphan_queries = {
        "stt_interactions:missing_organization": (
            "SELECT count(*) FROM stt_interactions i LEFT JOIN organizations o "
            "ON o.id=i.organization_id WHERE o.id IS NULL"
        ),
        "stt_recordings:missing_interaction": (
            "SELECT count(*) FROM stt_recordings r LEFT JOIN stt_interactions i "
            "ON i.organization_id=r.organization_id AND i.owner_id=r.owner_id "
            "AND i.interaction_id=r.interaction_id WHERE i.id IS NULL"
        ),
        "stt_transcripts:missing_interaction": (
            "SELECT count(*) FROM stt_transcripts t LEFT JOIN stt_interactions i "
            "ON i.organization_id=t.organization_id AND i.owner_id=t.owner_id "
            "AND i.interaction_id=t.interaction_id WHERE i.id IS NULL"
        ),
        "stt_stream_leases:missing_interaction": (
            "SELECT count(*) FROM stt_stream_leases s LEFT JOIN stt_interactions i "
            "ON i.organization_id=s.organization_id AND i.owner_id=s.owner_id "
            "AND i.interaction_id=s.interaction_id WHERE i.id IS NULL"
        ),
        "stt_stream_checkpoints:missing_interaction": (
            "SELECT count(*) FROM stt_stream_checkpoints s LEFT JOIN stt_interactions i "
            "ON i.organization_id=s.organization_id AND i.owner_id=s.owner_id "
            "AND i.interaction_id=s.interaction_id WHERE i.id IS NULL"
        ),
    }
    for key, statement in orphan_queries.items():
        count = bind.exec_driver_sql(statement).scalar_one()
        if count:
            invalid[key] = int(count)
    if invalid:
        details = ", ".join(
            f"{key}={count}" for key, count in sorted(invalid.items())
        )
        raise RuntimeError(
            "migration 066 requires evidence-backed STT tenant reconciliation: "
            + details
        )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _validate_ownership()
    op.create_foreign_key(
        "fk_stt_interactions_organization",
        "stt_interactions",
        "organizations",
        ["organization_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_stt_recordings_interaction_scope",
        "stt_recordings",
        "stt_interactions",
        ["organization_id", "owner_id", "interaction_id"],
        ["organization_id", "owner_id", "interaction_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_stt_transcripts_interaction_scope",
        "stt_transcripts",
        "stt_interactions",
        ["organization_id", "owner_id", "interaction_id"],
        ["organization_id", "owner_id", "interaction_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_stt_stream_leases_interaction_scope",
        "stt_stream_leases",
        "stt_interactions",
        ["organization_id", "owner_id", "interaction_id"],
        ["organization_id", "owner_id", "interaction_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_stt_stream_checkpoints_interaction_scope",
        "stt_stream_checkpoints",
        "stt_interactions",
        ["organization_id", "owner_id", "interaction_id"],
        ["organization_id", "owner_id", "interaction_id"],
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
        "fk_stt_stream_checkpoints_interaction_scope",
        "stt_stream_checkpoints",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_stt_stream_leases_interaction_scope",
        "stt_stream_leases",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_stt_transcripts_interaction_scope",
        "stt_transcripts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_stt_recordings_interaction_scope",
        "stt_recordings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_stt_interactions_organization",
        "stt_interactions",
        type_="foreignkey",
    )
