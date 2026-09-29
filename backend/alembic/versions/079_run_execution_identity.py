"""Persist executed release and review signal, including draft previews."""
from alembic import op
import sqlalchemy as sa

revision = '079'
down_revision = '078'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('run_history', sa.Column('executed_agent_version', sa.String(64), nullable=True))
    op.add_column('run_history', sa.Column('draft_preview', sa.Boolean(), nullable=True))
    op.add_column('run_history', sa.Column('manual_review_required', sa.Boolean(), nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM run_history WHERE executed_agent_version IS NOT NULL')).scalar_one():
        raise RuntimeError('Cannot discard recorded execution identities; archive evidence before downgrade.')
    for name in ('manual_review_required','draft_preview','executed_agent_version'):
        op.drop_column('run_history', name)
