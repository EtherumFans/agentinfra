"""Preserve full governed-provider runtime identifiers in audit records."""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def _resize(source: int, target: int) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("run_history") as batch:
            batch.alter_column(
                "runtime_mode", existing_type=sa.String(source),
                type_=sa.String(target), existing_nullable=False,
            )
    else:
        op.alter_column(
            "run_history", "runtime_mode", existing_type=sa.String(source),
            type_=sa.String(target), existing_nullable=False,
        )


def upgrade() -> None:
    _resize(48, 128)


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM run_history WHERE length(runtime_mode) > 48"
    )).scalar_one()
    if count:
        raise RuntimeError(
            "cannot downgrade 077: run_history.runtime_mode contains "
            f"{count} identifier(s) longer than 48 characters"
        )
    _resize(128, 48)
