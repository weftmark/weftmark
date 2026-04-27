"""add approved_by_email to users

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("approved_by_email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approved_by_email")
