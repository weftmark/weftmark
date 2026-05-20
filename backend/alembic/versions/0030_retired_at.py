"""Add retired_at to drafts and looms.

Revision ID: 0030_retired_at
Revises: 7d8e9f0a1b2c
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0030_retired_at"
down_revision = "7d8e9f0a1b2c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("looms", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("drafts", "retired_at")
    op.drop_column("looms", "retired_at")
