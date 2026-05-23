"""drop redundant ravelry_credentials_user_id_key unique constraint

The 0037 migration created both a column-level UNIQUE constraint
(ravelry_credentials_user_id_key) and a separate unique index
(ix_ravelry_credentials_user_id) on the same column.  The constraint is
redundant — the index alone enforces uniqueness.  alembic check detects
the orphaned constraint and fails; this migration removes it.

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-23
"""

from alembic import op

revision = "0044_ravelry_drop_dup_uq"
down_revision = "0043_yarn_ravelry_colorway_photo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ravelry_credentials_user_id_key", "ravelry_credentials", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("ravelry_credentials_user_id_key", "ravelry_credentials", ["user_id"])
