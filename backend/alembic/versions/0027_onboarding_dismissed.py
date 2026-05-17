"""Add onboarding_dismissed column to users

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-17
"""

import sqlalchemy as sa
from alembic import op

revision: str = "5b6c7d8e9f0a"
down_revision: str = "4a7b2c9d1e3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_dismissed", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_dismissed")
