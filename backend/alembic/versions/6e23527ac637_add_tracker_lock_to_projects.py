"""add tracker lock to projects

Revision ID: 6e23527ac637
Revises: 0001_squash_902
Create Date: 2026-07-20 17:31:51.978619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6e23527ac637'
down_revision: Union[str, None] = '0001_squash_902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("active_tracker_session_id", sa.String(length=64), nullable=True))
    op.add_column("projects", sa.Column("active_tracker_claimed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "active_tracker_claimed_at")
    op.drop_column("projects", "active_tracker_session_id")
