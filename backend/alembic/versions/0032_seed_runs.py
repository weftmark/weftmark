"""Add seed_runs table for dev clean-start tracking.

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-01
"""

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seed_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("seed_runs")
