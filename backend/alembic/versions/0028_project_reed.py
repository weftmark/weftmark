"""add reed_dents_per_inch to projects

Revision ID: 6c7d8e9f0a1b
Revises: 5b6c7d8e9f0a
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "6c7d8e9f0a1b"
down_revision: str = "5b6c7d8e9f0a"


def upgrade() -> None:
    op.add_column("projects", sa.Column("reed_dents_per_inch", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "reed_dents_per_inch")
