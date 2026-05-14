"""Add wif_colors to drafts

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("wif_colors", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("drafts", "wif_colors")
