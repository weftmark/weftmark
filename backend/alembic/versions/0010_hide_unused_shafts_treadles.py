"""add hide_unused_shafts_treadles to users and projects

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-10

"""

import sqlalchemy as sa

from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("hide_unused_shafts_treadles", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "projects",
        sa.Column("hide_unused_shafts_treadles", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "hide_unused_shafts_treadles")
    op.drop_column("projects", "hide_unused_shafts_treadles")
