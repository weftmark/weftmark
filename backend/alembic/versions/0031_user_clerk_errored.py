"""Add clerk_errored flag to users table.

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-30
"""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("clerk_errored", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "clerk_errored")
