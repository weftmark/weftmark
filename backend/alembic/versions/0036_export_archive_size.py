"""add archive_size_bytes to user_export_requests

Revision ID: 0036_export_archive_size
Revises: 0035_feedback_discussion_state
Create Date: 2026-05-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_export_archive_size"
down_revision = "0035_feedback_discussion_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_export_requests",
        sa.Column("archive_size_bytes", sa.BigInteger, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_export_requests", "archive_size_bytes")
