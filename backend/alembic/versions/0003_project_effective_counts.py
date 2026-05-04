"""Add effective_num_treadles and effective_num_shafts to projects.

Revision ID: b7e4f1a8c302
Revises: a3f8c2d19e74
Create Date: 2026-05-03

These columns store the highest treadle/shaft index actually used in the
[TREADLING] / [LIFTPLAN] sections of the WIF file, which may differ from the
declared metadata in [WEAVING]. Used for loom compatibility checks so that a
design that declares 11 treadles but only uses 1-10 can still be run on a
10-treadle loom.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e4f1a8c302"
down_revision: str | None = "a3f8c2d19e74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("effective_num_treadles", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("effective_num_shafts", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "effective_num_shafts")
    op.drop_column("projects", "effective_num_treadles")
