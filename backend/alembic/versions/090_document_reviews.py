"""Encrypted document review snapshots and append-only review events."""
from alembic import op
import sqlalchemy as sa
revision='090'
down_revision='089'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('document_reviews',sa.Column('id',sa.String(36),primary_key=True),sa.Column('organization_id',sa.String(12),sa.ForeignKey('organizations.id'),nullable=False),sa.Column('created_by',sa.String(128),nullable=False),sa.Column('request_id',sa.String(80),nullable=False),sa.Column('version',sa.Integer,nullable=False),sa.Column('status',sa.String(16),nullable=False),sa.Column('content',sa.Text,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('organization_id','created_by','request_id'))
    op.create_index('ix_document_reviews_organization_id','document_reviews',['organization_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE document_reviews ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE document_reviews FORCE ROW LEVEL SECURITY')
        tenant="organization_id = nullif(current_setting('icoder.current_organization_id',true),'')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON document_reviews USING ({tenant}) WITH CHECK ({tenant})')
        op.create_check_constraint('ck_document_review_encrypted','document_reviews',"content ~ '^v[0-9]+:'")
def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM document_reviews')).scalar_one():
        raise RuntimeError('Cannot discard document review history')
    op.drop_table('document_reviews')
