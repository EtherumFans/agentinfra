"""Hash persisted organization invitation credentials.

Revision ID: 041
Revises: 040
Create Date: 2026-08-15
"""

import hashlib

from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def _looks_like_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, token FROM organization_invites")
    ).mappings()
    for row in rows:
        token = row["token"]
        if token and not _looks_like_sha256(token):
            connection.execute(
                sa.text("UPDATE organization_invites SET token = :digest WHERE id = :id"),
                {
                    "digest": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    "id": row["id"],
                },
            )


def downgrade() -> None:
    # Raw bearer credentials cannot and must not be reconstructed.
    pass
