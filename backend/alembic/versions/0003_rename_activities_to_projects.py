"""Rename activities tables to projects.

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-04

Renames:
  activities          → projects
  activity_photos     → project_photos
  activity_steps      → project_steps
  activity_id column  → project_id (in project_photos and project_steps)
  activity_type col   → project_type (in projects)

Storage paths in project_photos.file_path are updated from
activities/{id}/... to projects/{id}/... via SQL.
Note: actual S3 object keys are NOT moved by this migration; a separate
script is needed for production if S3 objects need to be re-keyed.
"""

# ruff: noqa: E501
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename tables
    op.rename_table("activities", "projects")
    op.rename_table("activity_photos", "project_photos")
    op.rename_table("activity_steps", "project_steps")

    # Rename the activity_type column to project_type in projects
    op.alter_column("projects", "activity_type", new_column_name="project_type")

    # Rename FK columns activity_id → project_id
    op.alter_column("project_photos", "activity_id", new_column_name="project_id")
    op.alter_column("project_steps", "activity_id", new_column_name="project_id")

    # Rename indexes
    op.execute("ALTER INDEX ix_activities_owner_id RENAME TO ix_projects_owner_id")
    op.execute("ALTER INDEX ix_activities_draft_id RENAME TO ix_projects_draft_id")
    op.execute("ALTER INDEX ix_activity_photos_activity_id RENAME TO ix_project_photos_project_id")
    op.execute("ALTER INDEX ix_activity_steps_activity_id RENAME TO ix_project_steps_project_id")

    # Update storage paths: activities/{uuid}/... → projects/{uuid}/...
    op.execute(
        "UPDATE project_photos "
        "SET file_path = 'projects' || substring(file_path, 11) "
        "WHERE file_path LIKE 'activities/%'"
    )


def downgrade() -> None:
    # Restore storage paths
    op.execute(
        "UPDATE project_photos "
        "SET file_path = 'activities' || substring(file_path, 9) "
        "WHERE file_path LIKE 'projects/%'"
    )

    # Restore indexes
    op.execute("ALTER INDEX ix_projects_owner_id RENAME TO ix_activities_owner_id")
    op.execute("ALTER INDEX ix_projects_draft_id RENAME TO ix_activities_draft_id")
    op.execute("ALTER INDEX ix_project_photos_project_id RENAME TO ix_activity_photos_activity_id")
    op.execute("ALTER INDEX ix_project_steps_project_id RENAME TO ix_activity_steps_activity_id")

    # Restore FK columns
    op.alter_column("project_photos", "project_id", new_column_name="activity_id")
    op.alter_column("project_steps", "project_id", new_column_name="activity_id")

    # Restore project_type column
    op.alter_column("projects", "project_type", new_column_name="activity_type")

    # Restore table names
    op.rename_table("project_steps", "activity_steps")
    op.rename_table("project_photos", "activity_photos")
    op.rename_table("projects", "activities")
