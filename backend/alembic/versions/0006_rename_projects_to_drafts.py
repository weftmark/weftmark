"""rename projects table to drafts and update FK in activities

Revision ID: a1b2c3d4e5f6
Revises: d3b6a9e2f518
Create Date: 2026-05-03
"""

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "d3b6a9e2f518"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename the projects table to drafts
    op.rename_table("projects", "drafts")

    # Rename the FK column in activities: project_id -> draft_id
    op.alter_column("activities", "project_id", new_column_name="draft_id")

    # Rename the index on activities.project_id
    op.execute("ALTER INDEX IF EXISTS ix_activities_project_id RENAME TO ix_activities_draft_id")

    # Rename the owner_id index on drafts (was ix_projects_owner_id)
    op.execute("ALTER INDEX IF EXISTS ix_projects_owner_id RENAME TO ix_drafts_owner_id")

    # Rename the primary key index on drafts (was projects_pkey)
    op.execute("ALTER INDEX IF EXISTS projects_pkey RENAME TO drafts_pkey")

    # Rename the unique constraint on share_slug (IF EXISTS not supported for constraints)
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE drafts RENAME CONSTRAINT projects_share_slug_key TO drafts_share_slug_key;
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$
        """
    )

    # Rename the FK constraint on activities referencing projects
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE activities RENAME CONSTRAINT activities_project_id_fkey TO activities_draft_id_fkey;
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE activities RENAME CONSTRAINT activities_draft_id_fkey TO activities_project_id_fkey;
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE drafts RENAME CONSTRAINT drafts_share_slug_key TO projects_share_slug_key;
        EXCEPTION WHEN undefined_object THEN NULL;
        END $$
        """
    )
    op.execute("ALTER INDEX IF EXISTS drafts_pkey RENAME TO projects_pkey")
    op.execute("ALTER INDEX IF EXISTS ix_drafts_owner_id RENAME TO ix_projects_owner_id")
    op.execute("ALTER INDEX IF EXISTS ix_activities_draft_id RENAME TO ix_activities_project_id")
    op.alter_column("activities", "draft_id", new_column_name="project_id")
    op.rename_table("drafts", "projects")
