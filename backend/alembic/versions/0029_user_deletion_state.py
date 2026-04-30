"""add deletion_state and deletion_initiated_at to users

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deletion_state", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("deletion_initiated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deletion_initiated_at")
    op.drop_column("users", "deletion_state")
