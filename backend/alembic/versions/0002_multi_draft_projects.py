"""Multi-draft project sequence: add project_drafts table, migrate existing data, drop old columns.

Revision ID: 0002_multi_draft_projects
Revises: 0001_squash_902
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_multi_draft_projects"
down_revision: Union[str, None] = "0001_squash_902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create project_drafts sequence table
    op.create_table(
        "project_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("repeats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_pick", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "position", name="uq_project_draft_position"),
    )
    op.create_index("ix_project_drafts_project_id", "project_drafts", ["project_id"])
    op.create_index("ix_project_drafts_draft_id", "project_drafts", ["draft_id"])

    # 2. Add current_position to projects (nullable initially for the data migration step)
    op.add_column("projects", sa.Column("current_position", sa.Integer(), nullable=True))

    # 3. Add sequence_id to project_steps (nullable — existing steps have no sequence context)
    op.add_column(
        "project_steps",
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_drafts.id"), nullable=True),
    )
    op.create_index("ix_project_steps_sequence_id", "project_steps", ["sequence_id"])

    # 4. Migrate existing projects → create one project_drafts row per project
    #    Preserve current_pick from the old column into project_drafts.current_pick
    op.execute("""
        INSERT INTO project_drafts (id, project_id, draft_id, position, repeats, current_pick, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            p.id,
            p.draft_id,
            1,
            1,
            GREATEST(p.current_pick - 1, 0),
            NOW(),
            NOW()
        FROM projects p
        WHERE p.draft_id IS NOT NULL
          AND p.deleted_at IS NULL
    """)

    # Also handle soft-deleted projects
    op.execute("""
        INSERT INTO project_drafts (id, project_id, draft_id, position, repeats, current_pick, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            p.id,
            p.draft_id,
            1,
            1,
            GREATEST(p.current_pick - 1, 0),
            NOW(),
            NOW()
        FROM projects p
        WHERE p.draft_id IS NOT NULL
          AND p.deleted_at IS NOT NULL
    """)

    # 5. Set current_position = 1 for all projects
    op.execute("UPDATE projects SET current_position = 1")

    # 6. Make current_position NOT NULL with default
    op.alter_column("projects", "current_position", nullable=False, server_default="1")

    # 7. Make project_type nullable (new projects won't have it until loom is assigned)
    op.alter_column("projects", "project_type", nullable=True)

    # 8. Drop old columns from projects
    #    (draft_id, current_pick, total_picks are now in project_drafts)
    op.drop_index("ix_projects_draft_id", table_name="projects")
    op.drop_column("projects", "draft_id")
    op.drop_column("projects", "current_pick")
    op.drop_column("projects", "total_picks")


def downgrade() -> None:
    # Restore old columns (best-effort: populate from first sequence entry)
    op.add_column("projects", sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("current_pick", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("total_picks", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE projects p
        SET
            draft_id = pd.draft_id,
            current_pick = pd.current_pick + 1,
            total_picks = COALESCE(d.weft_threads, 1)
        FROM project_drafts pd
        JOIN drafts d ON d.id = pd.draft_id
        WHERE pd.project_id = p.id AND pd.position = 1
    """)

    op.alter_column("projects", "draft_id", nullable=False)
    op.alter_column("projects", "current_pick", nullable=False, server_default="1")
    op.alter_column("projects", "total_picks", nullable=False, server_default="1")
    op.create_index("ix_projects_draft_id", "projects", ["draft_id"])

    op.alter_column("projects", "project_type", nullable=False)

    op.drop_index("ix_project_steps_sequence_id", table_name="project_steps")
    op.drop_column("project_steps", "sequence_id")

    op.drop_column("projects", "current_position")

    op.drop_index("ix_project_drafts_draft_id", table_name="project_drafts")
    op.drop_index("ix_project_drafts_project_id", table_name="project_drafts")
    op.drop_table("project_drafts")
