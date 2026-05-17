"""Add global tracker preference columns to users

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-17
"""

import sqlalchemy as sa
from alembic import op

revision = "4a7b2c9d1e3f"
down_revision = "1c23e69db390"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tracker_color_mode", sa.String(10), nullable=False, server_default="strip"))
    op.add_column("users", sa.Column("tracker_show_weft_color", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("users", sa.Column("tracker_show_drawdown", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("users", sa.Column("tracker_show_progress", sa.Boolean, nullable=False, server_default="true"))
    op.add_column("users", sa.Column("tracker_show_pick_cards", sa.Boolean, nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("users", "tracker_show_pick_cards")
    op.drop_column("users", "tracker_show_progress")
    op.drop_column("users", "tracker_show_drawdown")
    op.drop_column("users", "tracker_show_weft_color")
    op.drop_column("users", "tracker_color_mode")
