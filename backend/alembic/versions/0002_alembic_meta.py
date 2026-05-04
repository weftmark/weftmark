"""Add alembic_meta tracking table

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-05-04

Lightweight key/value table used by entrypoint.sh to record when migrations
last ran, and by new migrations to update the squash date. The admin services
tab reads from this table to display DB info.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alembic_meta",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="alembic_meta_pkey"),
    )
    op.execute(
        "INSERT INTO alembic_meta (key, value) VALUES ('last_squash_at', '2026-05-04') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("alembic_meta")
