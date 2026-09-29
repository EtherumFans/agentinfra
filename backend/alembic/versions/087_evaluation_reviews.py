"""Organization-scoped evaluation review decisions."""
from alembic import op
import sqlalchemy as sa
revision='087'
down_revision='086'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('agent_evaluation_reviews',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('evaluation_id',sa.String(36),sa.ForeignKey('agent_evaluations.id'),nullable=False),
        sa.Column('decision',sa.String(16),nullable=False),sa.Column('note',sa.Text(),nullable=False),
        sa.Column('created_by',sa.String(128),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_agent_evaluation_reviews_organization_id','agent_evaluation_reviews',['organization_id'])
    op.create_index('ix_agent_evaluation_reviews_evaluation_id','agent_evaluation_reviews',['evaluation_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE agent_evaluation_reviews ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE agent_evaluation_reviews FORCE ROW LEVEL SECURITY')
        tenant="organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON agent_evaluation_reviews USING ({tenant}) WITH CHECK ({tenant})')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM agent_evaluation_reviews')).scalar_one():
        raise RuntimeError('Cannot discard evaluation review history')
    op.drop_table('agent_evaluation_reviews')
