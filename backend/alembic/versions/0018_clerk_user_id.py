"""add clerk_user_id to users; make oidc_sub nullable

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)

    # oidc_sub is no longer required — existing users keep their value;
    # new Clerk users will have NULL here.
    op.alter_column("users", "oidc_sub", nullable=True)


def downgrade() -> None:
    op.alter_column("users", "oidc_sub", nullable=False)
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
