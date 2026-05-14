"""Add warp_color_stats to drafts

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("warp_color_stats", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("drafts", "warp_color_stats")
