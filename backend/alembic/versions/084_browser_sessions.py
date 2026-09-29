"""Revocable browser authentication sessions (user-scoped auth data)."""
from alembic import op
import sqlalchemy as sa
revision='084'
down_revision='083'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('browser_sessions',sa.Column('id',sa.String(64),primary_key=True),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('revoked_at',sa.DateTime(timezone=True)))
    op.create_index('ix_browser_sessions_user_id','browser_sessions',['user_id'])
def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM browser_sessions')).scalar_one():
        raise RuntimeError('Cannot discard browser session revocation state; expire sessions before downgrade')
    op.drop_table('browser_sessions')
