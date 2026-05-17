"""Add project sharing: share_slug, share_visibility, share_expires_at

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa

revision = "f6e5d4c3b2a1"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("share_slug", sa.String(64), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "share_visibility",
            sa.String(10),
            nullable=False,
            server_default="private",
        ),
    )
    op.add_column(
        "projects",
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_projects_share_slug", "projects", ["share_slug"])
    op.create_index("ix_projects_share_slug", "projects", ["share_slug"])


def downgrade() -> None:
    op.drop_index("ix_projects_share_slug", table_name="projects")
    op.drop_constraint("uq_projects_share_slug", "projects", type_="unique")
    op.drop_column("projects", "share_expires_at")
    op.drop_column("projects", "share_visibility")
    op.drop_column("projects", "share_slug")
