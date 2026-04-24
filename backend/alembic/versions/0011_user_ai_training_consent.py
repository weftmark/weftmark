"""Add ai_training_consent to users (Phase 2 placeholder)

Defaults to False (opt-out). The data pipeline that consumes this flag
is Phase 2; the field is added now to avoid a migration during that work.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ai_training_consent", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "ai_training_consent")
