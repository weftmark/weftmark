"""Add loom_reeds table

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loom_reeds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("loom_id", UUID(as_uuid=True), sa.ForeignKey("looms.id"), nullable=False, index=True),
        sa.Column("dents_per_inch", sa.Float(), nullable=False),
        sa.Column("width_cm", sa.Float(), nullable=True),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("loom_reeds")
