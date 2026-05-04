"""rename ix_projects_owner_id index to ix_drafts_owner_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-04

Migration 0006 renamed the projects table to drafts but did not rename the
owner_id index. This migration handles databases where 0006 already ran
without that rename. On fresh databases 0006 already includes the rename,
so IF EXISTS silently skips here.
"""

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS ix_projects_owner_id RENAME TO ix_drafts_owner_id")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS ix_drafts_owner_id RENAME TO ix_projects_owner_id")
