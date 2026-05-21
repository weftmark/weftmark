"""add user_export_requests table

Revision ID: 0034_user_export_requests
Revises: 0033_loom_version_catalog_link
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0034_user_export_requests"
down_revision = "0033_loom_version_catalog_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_export_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("archive_path", sa.String(512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_export_requests_user_id", "user_export_requests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_export_requests_user_id", table_name="user_export_requests")
    op.drop_table("user_export_requests")
