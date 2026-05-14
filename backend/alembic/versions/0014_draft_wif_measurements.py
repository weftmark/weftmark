"""Add wif_measurements, warp_length_cm, warp_length_overridden to drafts

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("wif_measurements", JSONB(), nullable=True))
    op.add_column("drafts", sa.Column("warp_length_cm", sa.Float(), nullable=True))
    op.add_column(
        "drafts",
        sa.Column("warp_length_overridden", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("drafts", "warp_length_overridden")
    op.drop_column("drafts", "warp_length_cm")
    op.drop_column("drafts", "wif_measurements")
