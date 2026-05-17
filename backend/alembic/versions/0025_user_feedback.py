"""Add user_feedback table for in-app feedback submissions

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "1c23e69db390"
down_revision = "f6e5d4c3b2a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submission_type", sa.String(20), nullable=False),
        sa.Column("is_anonymous", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("diagnostics", JSONB, nullable=True),
        sa.Column("github_discussion_url", sa.Text, nullable=True),
        sa.Column("dispatch_status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("dispatch_error", sa.Text, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])
    op.create_index("ix_user_feedback_created_at", "user_feedback", ["created_at"])
    op.create_index("ix_user_feedback_dispatch_status", "user_feedback", ["dispatch_status"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_dispatch_status", table_name="user_feedback")
    op.drop_index("ix_user_feedback_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_user_id", table_name="user_feedback")
    op.drop_table("user_feedback")
