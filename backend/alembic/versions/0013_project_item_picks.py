"""Add item_picks to projects

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f6"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("item_picks", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("projects", "item_picks")
