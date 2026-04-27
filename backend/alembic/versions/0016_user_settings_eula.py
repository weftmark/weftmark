"""add eula acceptance tracking and activity_theme to users

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("activity_theme", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("eula_accepted_version", sa.String(20), nullable=True))
    op.add_column(
        "users",
        sa.Column("eula_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "eula_accepted_at")
    op.drop_column("users", "eula_accepted_version")
    op.drop_column("users", "activity_theme")
