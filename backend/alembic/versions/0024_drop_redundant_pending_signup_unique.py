"""drop redundant unique constraint on pending_signups.clerk_user_id

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-27

Migration 0019 created both an inline unique constraint
(pending_signups_clerk_user_id_key) and a unique index
(ix_pending_signups_clerk_user_id) on the same column.  SQLAlchemy's
mapped_column(unique=True, index=True) only generates the unique index,
not a standalone constraint, so alembic check detects schema drift.
Drop the redundant constraint so the DB matches the model.
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("pending_signups_clerk_user_id_key", "pending_signups", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("pending_signups_clerk_user_id_key", "pending_signups", ["clerk_user_id"])
