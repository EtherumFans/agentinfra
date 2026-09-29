"""Encrypted organization model connections."""
from alembic import op
import sqlalchemy as sa
revision = '085'
down_revision = '084'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('model_connections',
        sa.Column('organization_id', sa.String(12), sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('model', sa.String(80), nullable=False),
        sa.Column('encrypted_key', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('ALTER TABLE model_connections ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE model_connections FORCE ROW LEVEL SECURITY')
        tenant = "organization_id = nullif(current_setting('icoder.current_organization_id', true), '')"
        op.execute(f'CREATE POLICY icoder_tenant_isolation ON model_connections USING ({tenant}) WITH CHECK ({tenant})')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM model_connections')).scalar_one():
        raise RuntimeError('Remove model connections before downgrade')
    op.drop_table('model_connections')
