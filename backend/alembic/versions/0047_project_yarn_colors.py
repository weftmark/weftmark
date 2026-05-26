"""Add project_yarn_colors junction table

Revision ID: 0047_project_yarn_colors
Revises: 0046_yarn_attribute_ids
Create Date: 2026-05-25

Links yarn inventory entries to project color slots by hex key.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0047_project_yarn_colors"
down_revision = "0046_yarn_attribute_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_yarn_colors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "yarn_id",
            UUID(as_uuid=True),
            sa.ForeignKey("yarns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("color_hex", sa.String(7), nullable=False),
        sa.Column("use_yarn_photo", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "color_hex", name="uq_project_yarn_color"),
    )


def downgrade() -> None:
    op.drop_table("project_yarn_colors")
