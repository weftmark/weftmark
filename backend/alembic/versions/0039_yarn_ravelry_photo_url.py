"""Add ravelry_photo_url to yarns table.

Revision ID: 0039_yarn_ravelry_photo_url
Revises: 0038_fix_ravelry_timestamps
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_yarn_ravelry_photo_url"
down_revision = "0038_fix_ravelry_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("ravelry_photo_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("yarns", "ravelry_photo_url")
