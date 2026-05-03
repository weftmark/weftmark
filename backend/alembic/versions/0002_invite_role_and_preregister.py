"""Add role + user_id to invites for pre-registration support.

Revision ID: a3f8c2d19e74
Revises: 11f6119b07a0
Create Date: 2026-05-03

- invites.role: VARCHAR(20) NOT NULL DEFAULT 'user'
- invites.user_id: UUID nullable FK → users.id (pre-created User linked to the invite)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "a3f8c2d19e74"
down_revision: str | None = "11f6119b07a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invites", sa.Column("role", sa.String(20), nullable=False, server_default="user"))
    op.add_column(
        "invites",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invites", "user_id")
    op.drop_column("invites", "role")
