"""move loom_reference_id from looms to loom_versions

Revision ID: 0033_loom_version_catalog_link
Revises: 0032_tags
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0033_loom_version_catalog_link"
down_revision = "0032_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "loom_versions",
        sa.Column(
            "loom_reference_id",
            UUID(as_uuid=True),
            sa.ForeignKey("loom_references.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    # Copy existing loom-level catalog link to the latest version of each loom
    op.execute(
        """
        UPDATE loom_versions lv
        SET loom_reference_id = l.loom_reference_id
        FROM looms l
        WHERE lv.loom_id = l.id
          AND l.loom_reference_id IS NOT NULL
          AND lv.version_number = (
              SELECT MAX(v2.version_number)
              FROM loom_versions v2
              WHERE v2.loom_id = l.id
          )
        """
    )

    op.drop_constraint("fk_looms_loom_reference_id", "looms", type_="foreignkey")
    op.drop_index("ix_looms_loom_reference_id", table_name="looms")
    op.drop_column("looms", "loom_reference_id")


def downgrade() -> None:
    op.add_column(
        "looms",
        sa.Column(
            "loom_reference_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_looms_loom_reference_id",
        "looms",
        "loom_references",
        ["loom_reference_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_looms_loom_reference_id", "looms", ["loom_reference_id"])

    # Restore from latest version (best-effort)
    op.execute(
        """
        UPDATE looms l
        SET loom_reference_id = lv.loom_reference_id
        FROM loom_versions lv
        WHERE lv.loom_id = l.id
          AND lv.loom_reference_id IS NOT NULL
          AND lv.version_number = (
              SELECT MAX(v2.version_number)
              FROM loom_versions v2
              WHERE v2.loom_id = l.id
          )
        """
    )

    op.drop_column("loom_versions", "loom_reference_id")
