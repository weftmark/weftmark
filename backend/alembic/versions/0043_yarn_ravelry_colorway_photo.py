"""add ravelry_colorway_photo_url and ravelry_colorway_thumbnail_url to yarns

Revision ID: 0043_yarn_ravelry_colorway_photo
Revises: 0042_yarn_ravelry_thumbnail_url
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_yarn_ravelry_colorway_photo"
down_revision = "0042_yarn_ravelry_thumbnail_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("ravelry_colorway_photo_url", sa.Text, nullable=True))
    op.add_column("yarns", sa.Column("ravelry_colorway_thumbnail_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("yarns", "ravelry_colorway_photo_url")
    op.drop_column("yarns", "ravelry_colorway_thumbnail_url")
