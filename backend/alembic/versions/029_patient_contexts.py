"""patient_contexts — A1C.3 Patient Context API (closes RV.5 J8)

Phase A1C.3 (2026-07-25): implements the patient_contexts table per the
HIS_EMR_INTEGRATION_CONTRACT.md §2 design. Closes the RV.5
BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT gap by providing the POST
/api/v1/patient-context endpoint a backing store.

Fields are 1:1 with PATIENT_CONTEXT_SCHEMA.json. Hard 24h TTL enforced by
the `expires_at` column + the ix_patient_contexts_expires_at index (a
separate cron job will scan for expired rows).

Revision ID: 029
Revises: 028
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_contexts",
        sa.Column("id", sa.String(length=12), primary_key=True),
        sa.Column("organization_id", sa.String(length=12),
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("patient_id", sa.String(length=64), nullable=False),
        sa.Column("encounter_id", sa.String(length=64), nullable=True),
        sa.Column("visit_type", sa.String(length=32), nullable=False),
        sa.Column("department_id", sa.String(length=64), nullable=False),
        sa.Column("ward_id", sa.String(length=64), nullable=True),
        sa.Column("clinician_id", sa.String(length=64), nullable=False),
        sa.Column("document_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("purpose_of_use", sa.String(length=32), nullable=False),
        sa.Column("consent_legal_basis", sa.String(length=32), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False,
                  server_default="active"),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_patient_contexts_organization_id",
                    "patient_contexts", ["organization_id"])
    op.create_index("ix_patient_contexts_tenant_id",
                    "patient_contexts", ["tenant_id"])
    op.create_index("ix_patient_contexts_source_system",
                    "patient_contexts", ["source_system"])
    op.create_index("ix_patient_contexts_encounter_id",
                    "patient_contexts", ["encounter_id"])
    op.create_index("ix_patient_contexts_department_id",
                    "patient_contexts", ["department_id"])
    op.create_index("ix_patient_contexts_trace_id",
                    "patient_contexts", ["trace_id"])
    op.create_index("ix_patient_contexts_status",
                    "patient_contexts", ["status"])
    op.create_index("ix_patient_contexts_expires_at",
                    "patient_contexts", ["expires_at"])
    op.create_index("ix_patient_contexts_org_patient",
                    "patient_contexts", ["organization_id", "patient_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_contexts_org_patient", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_expires_at", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_status", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_trace_id", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_department_id", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_encounter_id", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_source_system", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_tenant_id", table_name="patient_contexts")
    op.drop_index("ix_patient_contexts_organization_id", table_name="patient_contexts")
    op.drop_table("patient_contexts")
