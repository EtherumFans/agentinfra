"""Align OAuth persistence with UTC-aware token issuance."""
from alembic import op
import sqlalchemy as sa
revision='081'
down_revision='080'
branch_labels=None
depends_on=None

def change(aware):
    if op.get_bind().dialect.name!='postgresql':return
    for table,column in (('oauth_clients','last_used_at'),('oauth_tokens','expires_at')):
        op.alter_column(table,column,type_=sa.DateTime(timezone=aware),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'")
def upgrade():change(True)
def downgrade():change(False)
