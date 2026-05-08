"""add server_events table

Revision ID: a4b5c6d7e8f9
Revises: 2385931d5a57
Create Date: 2026-05-08

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "2385931d5a57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_server_events_event_type", "server_events", ["event_type"])
    op.create_index("ix_server_events_started_at", "server_events", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_server_events_started_at", table_name="server_events")
    op.drop_index("ix_server_events_event_type", table_name="server_events")
    op.drop_table("server_events")
