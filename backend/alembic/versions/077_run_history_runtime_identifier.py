"""Preserve full governed-provider runtime identifiers in audit records."""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def _resize(source: int, target: int) -> None:
    if op.get_bind().dialect.name == "sqlite":
        # A process interrupted before batch-copy may leave an empty shadow
        # table. Only discard that empty scaffold while the authoritative
        # table still exists; preserve ambiguous/populated recovery state.
        inspector = sa.inspect(op.get_bind())
        if inspector.has_table("_alembic_tmp_run_history"):
            shadow_rows = op.get_bind().execute(sa.text(
                "SELECT COUNT(*) FROM _alembic_tmp_run_history"
            )).scalar_one()
            if shadow_rows or not inspector.has_table("run_history"):
                raise RuntimeError(
                    "cannot resume 077: preserved SQLite batch shadow "
                    "requires manual recovery"
                )
            op.drop_table("_alembic_tmp_run_history")
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
