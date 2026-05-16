"""Add drawdown_svg_path to projects

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("drawdown_svg_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "drawdown_svg_path")
