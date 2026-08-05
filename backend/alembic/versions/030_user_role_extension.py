"""UserRole enum extension — A1D.3 A1C-B-020

Phase A1D.3 (2026-08-05): closes the A1C.4 §3.1 deferral by adding 2 new
UserRole enum values:

  - ``CDI_SPECIALIST`` (cdi_specialist) — CDI 专员, previously conflated
    with ``QC`` (质控科). The two principals have distinct responsibilities
    per Corti-style hospital role taxonomy: CDI drives provider-query +
    documentation completeness; QC drives post-coding quality review.

  - ``MEDICAL_RECORDS_ADMIN`` (medical_records_admin) — 病案管理员, previously
    conflated with ``DEPT_HEAD`` (科室负责人). The two principals differ:
    MRA owns the medical-records archive + chart-completion enforcement
    across the hospital; DEPT_HEAD owns a single department's clinical
    operations.

Schema change: SQLite stores ``Enum(UserRole)`` as a CHECK constraint
listing allowed literals. The CHECK constraint must be widened to accept
the 2 new values. PostgreSQL uses native ENUM type — ``ALTER TYPE`` adds
the new values without table rewrite.

No data backfill: existing rows keep their ``QC`` / ``DEPT_HEAD`` values.
New rows opt into the new roles via the registration / SSO mapping layer
(A1C.4 §3.3 SSO_INTEGRATION_TEST_RESULTS).

Revision ID: 030
Revises: 029
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


# Allowed literals — must match app.models.user.UserRole values exactly.
# Keep this list in sync with the Python enum.
_USER_ROLE_LITERALS = [
    "admin",
    "coder",
    "dept_head",
    "insurance",
    "qc",
    "clinician",
    "it",
    # Phase A1D.3 (A1C-B-020) — new
    "cdi_specialist",
    "medical_records_admin",
]


def upgrade() -> None:
    """Widen users.role CHECK constraint to accept the 2 new role literals.

    SQLite: batch_alter_table recreates the column with the new CHECK.
    PostgreSQL: native ENUM type — ALTER TYPE ADD VALUE.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.Enum(*_USER_ROLE_LITERALS, name="userrole"),
                type_=sa.Enum(*_USER_ROLE_LITERALS, name="userrole"),
                existing_nullable=False,
                existing_server_default="coder",
            )
    elif dialect == "postgresql":
        # Native ENUM — additive, no table rewrite.
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'cdi_specialist'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'medical_records_admin'")
    else:
        # MySQL / others: fall back to alter_column; let the dialect decide.
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.Enum(*_USER_ROLE_LITERALS, name="userrole"),
                type_=sa.Enum(*_USER_ROLE_LITERALS, name="userrole"),
                existing_nullable=False,
                existing_server_default="coder",
            )


def downgrade() -> None:
    """Revert users.role CHECK to the original 7 literals.

    NOTE: downgrade is informational only — iCoDer charter §6.1 forbids
    destructive git ops and DB downgrades in production. This is provided
    for parity with the alembic chain shape; operators should NOT run it
    on a populated DB.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        original = [v for v in _USER_ROLE_LITERALS if v not in (
            "cdi_specialist", "medical_records_admin",
        )]
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.Enum(*_USER_ROLE_LITERALS, name="userrole"),
                type_=sa.Enum(*original, name="userrole"),
                existing_nullable=False,
                existing_server_default="coder",
            )
    # PostgreSQL ENUM type cannot remove values without recreating the type
    # (PG enum has no DROP VALUE). Skip downgrade on PG — operators must
    # dump+restore if truly needed.
