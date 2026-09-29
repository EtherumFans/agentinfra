"""Persist observed model usage independently of legacy billing fields."""
from alembic import op
import sqlalchemy as sa
revision = '086'
down_revision = '085'
branch_labels = None
depends_on = None

FIELDS = [('model_calls', sa.Integer), ('model_input_tokens', sa.Integer),
          ('model_output_tokens', sa.Integer), ('model_estimated_cost_usd', sa.Float),
          ('model_usage_complete', sa.Boolean), ('model_cost_complete', sa.Boolean),
          ('model_usage', sa.JSON)]

def upgrade():
    for name, kind in FIELDS:
        op.add_column('run_history', sa.Column(name, kind(), nullable=True))

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM run_history WHERE model_calls IS NOT NULL')).scalar_one():
        raise RuntimeError('Cannot discard recorded model usage')
    for name, _ in reversed(FIELDS):
        op.drop_column('run_history', name)
