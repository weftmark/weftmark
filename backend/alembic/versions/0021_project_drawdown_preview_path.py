"""Add drawdown_preview_path to projects

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("drawdown_preview_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "drawdown_preview_path")
