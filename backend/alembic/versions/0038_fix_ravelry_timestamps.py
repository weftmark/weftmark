"""Fix missing server_default on ravelry_credentials timestamps.

Revision ID: 0038_fix_ravelry_timestamps
Revises: 0037_ravelry_integration
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0038_fix_ravelry_timestamps"
down_revision = "0037_ravelry_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ravelry_credentials",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "ravelry_credentials",
        "updated_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ravelry_credentials",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "ravelry_credentials",
        "updated_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
