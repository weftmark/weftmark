"""loom_type and user measurement_system

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add loom_type to looms
    op.add_column("looms", sa.Column("loom_type", sa.String(30), nullable=False, server_default="floor_loom"))

    # Make num_shafts and num_treadles nullable in loom_versions
    op.alter_column("loom_versions", "num_shafts", existing_type=sa.Integer, nullable=True)
    op.alter_column("loom_versions", "num_treadles", existing_type=sa.Integer, nullable=True)

    # Add num_heddles to loom_versions
    op.add_column("loom_versions", sa.Column("num_heddles", sa.Integer, nullable=True))

    # Add measurement_system to users
    op.add_column("users", sa.Column("measurement_system", sa.String(10), nullable=False, server_default="metric"))


def downgrade() -> None:
    op.drop_column("users", "measurement_system")
    op.drop_column("loom_versions", "num_heddles")
    op.alter_column("loom_versions", "num_treadles", existing_type=sa.Integer, nullable=False)
    op.alter_column("loom_versions", "num_shafts", existing_type=sa.Integer, nullable=False)
    op.drop_column("looms", "loom_type")
