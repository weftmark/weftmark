"""Add machine_washable to yarns; backfill from ravelry_machine_washable

Revision ID: 0045_yarn_machine_washable
Revises: 0044_ravelry_drop_dup_uq
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_yarn_machine_washable"
down_revision = "0044_ravelry_drop_dup_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("machine_washable", sa.Boolean(), nullable=True))
    op.execute(
        "UPDATE yarns SET machine_washable = ravelry_machine_washable "
        "WHERE ravelry_machine_washable IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("yarns", "machine_washable")
