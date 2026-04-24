"""version name and accessories

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Optional user-facing name on each configuration version
    op.add_column("loom_versions", sa.Column("name", sa.String(255), nullable=True))

    # Accessories — lightweight per-version item list, independent of spec changes
    op.create_table(
        "loom_version_accessories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loom_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loom_version_accessories_version_id", "loom_version_accessories", ["loom_version_id"])


def downgrade() -> None:
    op.drop_table("loom_version_accessories")
    op.drop_column("loom_versions", "name")
