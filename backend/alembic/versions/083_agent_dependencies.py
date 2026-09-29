"""External dependency revision registry with tenant isolation."""
from alembic import op
import sqlalchemy as sa
revision='083'
down_revision='082'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('agent_dependencies',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('kind',sa.String(16),nullable=False),sa.Column('name',sa.String(100),nullable=False),
        sa.Column('version',sa.String(100),nullable=False),sa.Column('artifact_digest',sa.String(64)),
        sa.Column('is_current',sa.Boolean(),nullable=False),sa.Column('created_by',sa.String(128),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('organization_id','kind','name','version',name='uq_dependency_revision'))
    op.create_index('ix_agent_dependencies_organization_id','agent_dependencies',['organization_id'])
    op.create_index('uq_dependency_current','agent_dependencies',['organization_id','kind','name'],unique=True,postgresql_where=sa.text('is_current'),sqlite_where=sa.text('is_current=1'))
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE agent_dependencies ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE agent_dependencies FORCE ROW LEVEL SECURITY')
        tenant="organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON agent_dependencies USING ({tenant}) WITH CHECK ({tenant})')

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM agent_dependencies')).scalar_one():raise RuntimeError('Cannot discard dependency history')
    op.drop_table('agent_dependencies')
