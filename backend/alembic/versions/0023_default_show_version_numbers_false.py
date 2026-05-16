"""Default show_version_numbers to false and backfill existing users

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-16
"""

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET show_version_numbers = false")
    op.execute("ALTER TABLE users ALTER COLUMN show_version_numbers SET DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN show_version_numbers SET DEFAULT true")
