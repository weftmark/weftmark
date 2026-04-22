"""projects

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("wif_filename", sa.String(512), nullable=False),
        sa.Column("wif_path", sa.String(512), nullable=False),
        sa.Column("num_shafts", sa.Integer, nullable=True),
        sa.Column("num_treadles", sa.Integer, nullable=True),
        sa.Column("warp_threads", sa.Integer, nullable=True),
        sa.Column("weft_threads", sa.Integer, nullable=True),
        sa.Column("has_threading", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("has_tieup", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("has_treadling", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("has_liftplan", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("has_color_palette", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("lint_warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("lint_errors", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("wif_source_software", sa.String(255), nullable=True),
        sa.Column("wif_source_version", sa.String(100), nullable=True),
        sa.Column("preview_path", sa.String(512), nullable=True),
        sa.Column("is_shared", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("share_slug", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_slug"),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])


def downgrade() -> None:
    op.drop_table("projects")
