"""add weave_sessions table and dwell_ms to project_steps

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-12

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weave_sessions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_weave_sessions_project_id", "weave_sessions", ["project_id"])
    op.add_column(
        "project_steps",
        sa.Column("dwell_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_steps", "dwell_ms")
    op.drop_index("ix_weave_sessions_project_id", table_name="weave_sessions")
    op.drop_table("weave_sessions")
