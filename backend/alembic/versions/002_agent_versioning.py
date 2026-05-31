"""Agent versioning + marketplace

Revision ID: 002
Revises: afeb04d02665
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = 'afeb04d02665'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agents', sa.Column('version', sa.String(20), nullable=False, server_default='1.0.0'))
    op.add_column('agents', sa.Column('status', sa.String(20), nullable=False, server_default='draft'))
    op.create_index(op.f('ix_agents_status'), 'agents', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_agents_status'), table_name='agents')
    op.drop_column('agents', 'status')
    op.drop_column('agents', 'version')
