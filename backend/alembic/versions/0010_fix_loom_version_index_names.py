"""Fix loom version FK index names to match SQLAlchemy auto-naming convention

The indexes on loom_version_photos, loom_version_receipts, and
loom_version_accessories were created with a shortened suffix (_version_id)
but SQLAlchemy auto-generates the name from the full column name
(loom_version_id), producing _loom_version_id. Rename to remove the drift.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-25
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER INDEX ix_loom_version_photos_version_id "
        "RENAME TO ix_loom_version_photos_loom_version_id"
    )
    op.execute(
        "ALTER INDEX ix_loom_version_receipts_version_id "
        "RENAME TO ix_loom_version_receipts_loom_version_id"
    )
    op.execute(
        "ALTER INDEX ix_loom_version_accessories_version_id "
        "RENAME TO ix_loom_version_accessories_loom_version_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER INDEX ix_loom_version_photos_loom_version_id "
        "RENAME TO ix_loom_version_photos_version_id"
    )
    op.execute(
        "ALTER INDEX ix_loom_version_receipts_loom_version_id "
        "RENAME TO ix_loom_version_receipts_version_id"
    )
    op.execute(
        "ALTER INDEX ix_loom_version_accessories_loom_version_id "
        "RENAME TO ix_loom_version_accessories_version_id"
    )
