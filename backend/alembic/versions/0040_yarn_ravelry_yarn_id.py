"""add ravelry_yarn_id to yarns

Revision ID: 0040_yarn_ravelry_yarn_id
Revises: 0039_yarn_ravelry_photo_url
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_yarn_ravelry_yarn_id"
down_revision = "0039_yarn_ravelry_photo_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("ravelry_yarn_id", sa.BigInteger, nullable=True))
    op.create_index("ix_yarns_ravelry_yarn_id", "yarns", ["ravelry_yarn_id"])


def downgrade() -> None:
    op.drop_index("ix_yarns_ravelry_yarn_id", table_name="yarns")
    op.drop_column("yarns", "ravelry_yarn_id")
