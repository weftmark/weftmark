"""Add wif_liftplan_path to projects.

Revision ID: c9a2e5f0b416
Revises: b7e4f1a8c302
Create Date: 2026-05-03

Stores the path to the liftplan-augmented WIF file separately from the original
wif_path so the original upload is never overwritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9a2e5f0b416"
down_revision: str | None = "b7e4f1a8c302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("wif_liftplan_path", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "wif_liftplan_path")
