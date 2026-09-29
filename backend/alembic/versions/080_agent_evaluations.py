"""Tenant-scoped immutable evaluation evidence."""
from alembic import op
import sqlalchemy as sa
revision='080'
down_revision='079'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('agent_evaluations',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(12),nullable=False),
        sa.Column('agent_id',sa.String(128),nullable=False),
        sa.Column('report',sa.JSON(),nullable=False),
        sa.Column('created_by',sa.String(128),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id'],ondelete='CASCADE'))
    op.create_index('ix_agent_evaluations_organization_id','agent_evaluations',['organization_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE agent_evaluations ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE agent_evaluations FORCE ROW LEVEL SECURITY')
        tenant="organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON agent_evaluations USING ({tenant}) WITH CHECK ({tenant})')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM agent_evaluations')).scalar_one():
        raise RuntimeError('Cannot discard evaluation evidence.')
    op.drop_table('agent_evaluations')
