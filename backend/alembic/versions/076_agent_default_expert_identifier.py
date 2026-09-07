"""Preserve full Pack expert identifiers in the Registry DB projection."""

from alembic import op
import sqlalchemy as sa

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def _resize(source: int, target: int) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("agents") as batch:
            batch.alter_column(
                "default_expert_id", existing_type=sa.String(source),
                type_=sa.String(target), existing_nullable=False,
            )
    else:
        op.alter_column(
            "agents", "default_expert_id", existing_type=sa.String(source),
            type_=sa.String(target), existing_nullable=False,
        )


def upgrade() -> None:
    _resize(12, 128)


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM agents WHERE length(default_expert_id) > 12"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "cannot downgrade 076: agents.default_expert_id contains "
            f"{count} identifier(s) longer than 12 characters"
        )
    _resize(128, 12)
