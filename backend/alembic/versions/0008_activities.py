"""activities

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loom_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("loom_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("activity_type", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("current_pick", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_picks", sa.Integer(), nullable=False),
        sa.Column("finished_length_per_item", sa.Numeric(8, 1), nullable=True),
        sa.Column("num_items", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("waste_between_items", sa.Numeric(8, 1), nullable=True),
        sa.Column("warp_waste_allowance", sa.Numeric(8, 1), nullable=True),
        sa.Column("length_unit", sa.String(5), nullable=False, server_default="cm"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["loom_id"], ["looms.id"]),
        sa.ForeignKeyConstraint(["loom_version_id"], ["loom_versions.id"]),
    )
    op.create_index("ix_activities_owner_id", "activities", ["owner_id"])
    op.create_index("ix_activities_project_id", "activities", ["project_id"])

    op.create_table(
        "activity_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column("from_pick", sa.Integer(), nullable=False),
        sa.Column("to_pick", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
    )
    op.create_index("ix_activity_steps_activity_id", "activity_steps", ["activity_id"])


def downgrade() -> None:
    op.drop_table("activity_steps")
    op.drop_table("activities")
