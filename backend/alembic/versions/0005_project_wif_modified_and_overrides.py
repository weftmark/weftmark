"""Rename wif_liftplan_path to wif_modified_path; add metadata_overrides.

Revision ID: d3b6a9e2f518
Revises: c9a2e5f0b416
Create Date: 2026-05-03

- Renames wif_liftplan_path -> wif_modified_path so the column reflects its
  broader purpose (liftplan generation, metadata overrides, future tools)
- Adds metadata_overrides JSONB to record user-initiated WIF metadata changes,
  e.g. {"num_treadles": {"original": 11, "override": 10}}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3b6a9e2f518"
down_revision: str | None = "c9a2e5f0b416"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("projects", "wif_liftplan_path", new_column_name="wif_modified_path")
    op.add_column("projects", sa.Column("metadata_overrides", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "metadata_overrides")
    op.alter_column("projects", "wif_modified_path", new_column_name="wif_liftplan_path")
