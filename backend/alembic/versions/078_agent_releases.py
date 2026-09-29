"""Published Agent snapshots with tenant isolation."""
from alembic import op
import sqlalchemy as sa

revision = '078'
down_revision = '077'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('agent_releases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(12), nullable=False),
        sa.Column('agent_id', sa.String(128), nullable=False),
        sa.Column('version', sa.String(64), nullable=False),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('runtime_pack', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id','agent_id','version',name='uq_agent_release_version'),
        sa.ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id'],ondelete='CASCADE'),
    )
    op.create_index('ix_agent_releases_organization_id','agent_releases',['organization_id'])
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE agent_releases ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE agent_releases FORCE ROW LEVEL SECURITY')
        tenant = "organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON agent_releases USING ({tenant}) WITH CHECK ({tenant})')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM agent_releases')).scalar_one():
        raise RuntimeError('Cannot discard published releases; archive/export before downgrade.')
    op.drop_table('agent_releases')
