"""add tags to drafts and projects

Revision ID: 0032_tags
Revises: 0031_collections
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032_tags"
down_revision = "0031_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("tags", JSONB, nullable=False, server_default="[]"))
    op.add_column("projects", sa.Column("tags", JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("drafts", "tags")
    op.drop_column("projects", "tags")
