"""loom photos and receipts

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Profile photo on loom
    op.add_column("looms", sa.Column("photo_path", sa.String(500), nullable=True))

    # Per-version photos
    op.create_table(
        "loom_version_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loom_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loom_version_photos_version_id", "loom_version_photos", ["loom_version_id"])

    # Per-version receipts
    op.create_table(
        "loom_version_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loom_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loom_version_receipts_version_id", "loom_version_receipts", ["loom_version_id"])


def downgrade() -> None:
    op.drop_table("loom_version_receipts")
    op.drop_table("loom_version_photos")
    op.drop_column("looms", "photo_path")
