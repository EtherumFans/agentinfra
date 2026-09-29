"""Persistent versioned datasets and resumable batch evaluations."""
from alembic import op
import sqlalchemy as sa
revision='089'
down_revision='088'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('evaluation_datasets',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),sa.Column('dataset_id',sa.String(36),nullable=False),sa.Column('version',sa.Integer,nullable=False),sa.Column('name',sa.String(120),nullable=False),sa.Column('split',sa.String(16),nullable=False),sa.Column('cases',sa.Text,nullable=False),sa.Column('digest',sa.String(64),nullable=False),sa.Column('case_count',sa.Integer,nullable=False),sa.Column('review_status',sa.String(16),nullable=False),sa.Column('reviews',sa.JSON,nullable=False),sa.Column('created_by',sa.String(128),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('organization_id','dataset_id','version'))
    op.create_table('evaluation_batches',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),sa.Column('agent_id',sa.String(128),nullable=False),sa.Column('dataset_revision_id',sa.String(36),sa.ForeignKey('evaluation_datasets.id'),nullable=False),sa.Column('draft_digest',sa.String(64),nullable=False),sa.Column('purpose',sa.String(32),nullable=False),sa.Column('request_id',sa.String(80),nullable=False),sa.Column('created_by',sa.String(128),nullable=False),sa.Column('state',sa.String(16),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('organization_id','created_by','request_id'),sa.ForeignKeyConstraint(['organization_id','agent_id'],['agents.organization_id','agents.id']))
    op.create_table('evaluation_batch_items',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),sa.Column('batch_id',sa.String(36),sa.ForeignKey('evaluation_batches.id'),nullable=False),sa.Column('case_index',sa.Integer,nullable=False),sa.Column('case_id',sa.String(80),nullable=False),sa.Column('state',sa.String(16),nullable=False),sa.Column('claim_token',sa.String(36)),sa.Column('lease_until',sa.DateTime(timezone=True)),sa.Column('result',sa.JSON),sa.Column('error_code',sa.String(80)),sa.Column('attempts',sa.JSON,nullable=False),sa.UniqueConstraint('batch_id','case_index'))
    for table,cols in {'evaluation_datasets':['organization_id','dataset_id'],'evaluation_batches':['organization_id'],'evaluation_batch_items':['organization_id','batch_id','state']}.items():
        for col in cols:op.create_index('ix_'+table+'_'+col,table,[col])
        if op.get_bind().dialect.name=='postgresql':
            op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY');op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
            tenant="organization_id = nullif(current_setting('icoder.current_organization_id',true),'')"
            op.execute(f'CREATE POLICY icoder_tenant_isolation ON {table} USING ({tenant}) WITH CHECK ({tenant})')
    if op.get_bind().dialect.name=='postgresql':op.create_check_constraint('ck_evaluation_dataset_encrypted','evaluation_datasets',"cases ~ '^v[0-9]+:'")

def downgrade():
    for table in ('evaluation_batch_items','evaluation_batches','evaluation_datasets'):
        if op.get_bind().execute(sa.text(f'SELECT count(*) FROM {table}')).scalar_one():raise RuntimeError('Cannot discard dataset or batch history')
    for table in ('evaluation_batch_items','evaluation_batches','evaluation_datasets'):op.drop_table(table)
