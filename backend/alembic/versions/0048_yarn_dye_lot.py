"""Add dye_lot to yarns

Revision ID: 0048_yarn_dye_lot
Revises: 0047_project_yarn_colors
Create Date: 2026-05-26

Adds optional dye_lot field to yarn records for Ravelry stash push-back.
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_yarn_dye_lot"
down_revision = "0047_project_yarn_colors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("dye_lot", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("yarns", "dye_lot")
