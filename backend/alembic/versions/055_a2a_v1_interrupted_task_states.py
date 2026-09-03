"""Add A2A v1 interrupted and rejected Task states.

Revision ID: 055
Revises: 054
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa


revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


_V1_STATE_CHECK = (
    "state IN ('submitted', 'working', 'completed', 'failed', 'canceled', "
    "'rejected', 'input-required', 'auth-required')"
)
_LEGACY_STATE_CHECK = (
    "state IN ('submitted', 'working', 'completed', 'failed', 'canceled')"
)


def _replace_state_check(expression: str) -> None:
    bind = op.get_bind()
    check_names = {
        str(item.get("name") or "")
        for item in sa.inspect(bind).get_check_constraints("context_task_refs")
    }
    if bind.dialect.name == "postgresql":
        # Replacing only the CHECK avoids recreating the table and its primary
        # key, which is referenced by a2a_task_artifacts in PostgreSQL.
        if "ck_context_task_refs_state" in check_names:
            op.drop_constraint(
                "ck_context_task_refs_state", "context_task_refs", type_="check"
            )
        op.create_check_constraint(
            "ck_context_task_refs_state", "context_task_refs", expression
        )
        return

    # SQLite cannot replace CHECK constraints with ALTER TABLE, so retain
    # Alembic's table-recreation path for that development database.
    with op.batch_alter_table("context_task_refs", recreate="always") as batch_op:
        if "ck_context_task_refs_state" in check_names:
            batch_op.drop_constraint("ck_context_task_refs_state", type_="check")
        batch_op.create_check_constraint("ck_context_task_refs_state", expression)


def upgrade() -> None:
    _replace_state_check(_V1_STATE_CHECK)


def downgrade() -> None:
    incompatible = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM context_task_refs "
        "WHERE state IN ('rejected', 'input-required', 'auth-required')"
    )).scalar_one()
    if incompatible:
        raise RuntimeError(
            "Cannot downgrade revision 055 while A2A v1-only Task states exist"
        )
    _replace_state_check(_LEGACY_STATE_CHECK)
