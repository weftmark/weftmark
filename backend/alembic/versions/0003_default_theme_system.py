"""Change users.theme column default from 'light' to 'system'.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-07

Changes:
- users.theme: server default changed from 'light' to 'system'

Existing rows are not modified — we cannot distinguish users who explicitly
chose light mode from those who received the old default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "theme",
        existing_type=sa.String(20),
        server_default="system",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "theme",
        existing_type=sa.String(20),
        server_default="light",
        existing_nullable=False,
    )
