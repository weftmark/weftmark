"""fix ai_training_consent server_default to true; backfill existing rows

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "ai_training_consent",
        server_default=sa.text("true"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
    op.execute("UPDATE users SET ai_training_consent = TRUE")


def downgrade() -> None:
    op.alter_column(
        "users",
        "ai_training_consent",
        server_default=sa.text("false"),
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )
