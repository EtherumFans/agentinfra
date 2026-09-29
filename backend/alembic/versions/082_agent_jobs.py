"""Durable agent jobs and notification outbox."""
from alembic import op
import sqlalchemy as sa
revision='082'
down_revision='081'
branch_labels=None
depends_on=None

def upgrade():
    columns=[sa.Column('id',sa.String(36),primary_key=True)]
    for name,length in [('organization_id',12),('agent_id',128),('actor_kind',12),('actor_id',128),('idempotency_key',150),('request_digest',64),('version',64),('state',32),('notification_state',20)]:
        columns.append(sa.Column(name,sa.String(length),nullable=False))
    columns.extend([sa.Column('payload',sa.Text(),nullable=False),sa.Column('result',sa.Text()),sa.Column('run_id',sa.String(64)),sa.Column('error_code',sa.String(80)),sa.Column('callback_url',sa.Text()),sa.Column('notification_attempts',sa.Integer(),nullable=False)])
    for name in ('created_at','finished_at','lease_until','notification_due','notification_lease'):
        columns.append(sa.Column(name,sa.DateTime(timezone=True),nullable=name!='created_at'))
    op.create_table('agent_jobs',*columns,
        sa.ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id'],ondelete='CASCADE'),
        sa.UniqueConstraint('organization_id','actor_kind','actor_id','idempotency_key',name='uq_agent_job_request'))
    op.create_index('ix_agent_jobs_organization_id','agent_jobs',['organization_id'])
    op.create_index('ix_agent_jobs_state','agent_jobs',['state'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE agent_jobs ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE agent_jobs FORCE ROW LEVEL SECURITY')
        tenant="organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON agent_jobs USING ({tenant}) WITH CHECK ({tenant})')
        op.create_check_constraint('ck_agent_jobs_payload_encrypted','agent_jobs',"payload ~ '^v[0-9]+:'")
        op.create_check_constraint('ck_agent_jobs_result_encrypted','agent_jobs',"result IS NULL OR result ~ '^v[0-9]+:'")

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM agent_jobs')).scalar_one():raise RuntimeError('Cannot discard job evidence')
    op.drop_table('agent_jobs')
