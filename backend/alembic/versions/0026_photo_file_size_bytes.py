"""add file_size_bytes to activity_photos and loom_version_photos

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_photos",
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "loom_version_photos",
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("activity_photos", "file_size_bytes")
    op.drop_column("loom_version_photos", "file_size_bytes")
