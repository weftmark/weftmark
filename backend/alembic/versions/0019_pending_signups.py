"""add pending_signups table

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_signups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pending_signups_clerk_user_id", "pending_signups", ["clerk_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_pending_signups_clerk_user_id", table_name="pending_signups")
    op.drop_table("pending_signups")
