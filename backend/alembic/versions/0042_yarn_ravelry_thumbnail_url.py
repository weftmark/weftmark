"""add ravelry_thumbnail_url to yarns

Revision ID: 0042_yarn_ravelry_thumbnail_url
Revises: 0041_yarn_ravelry_enrichment
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_yarn_ravelry_thumbnail_url"
down_revision = "0041_yarn_ravelry_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("ravelry_thumbnail_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("yarns", "ravelry_thumbnail_url")
