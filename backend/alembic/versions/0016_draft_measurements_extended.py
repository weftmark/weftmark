"""Add weaving_width_override_cm and epi_override to drafts

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("weaving_width_override_cm", sa.Float(), nullable=True))
    op.add_column("drafts", sa.Column("epi_override", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("drafts", "epi_override")
    op.drop_column("drafts", "weaving_width_override_cm")
