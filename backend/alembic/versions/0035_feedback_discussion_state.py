"""add github_discussion_state to user_feedback

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_feedback",
        sa.Column("github_discussion_state", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_feedback", "github_discussion_state")
