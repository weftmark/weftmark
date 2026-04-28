"""add approved_by_name to users

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("approved_by_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approved_by_name")
