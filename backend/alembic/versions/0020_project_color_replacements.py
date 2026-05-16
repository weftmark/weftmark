"""Add color_replacements to projects

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("color_replacements", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "color_replacements")
