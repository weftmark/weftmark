"""Add yarn_attribute_ids JSONB column to yarns

Revision ID: 0046_yarn_attribute_ids
Revises: 0045_yarn_machine_washable
Create Date: 2026-05-23

Stores a JSON array of Ravelry yarn attribute IDs (ints) on each yarn.
Both Ravelry-synced and manually-created yarns can carry these.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0046_yarn_attribute_ids"
down_revision = "0045_yarn_machine_washable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "yarns",
        sa.Column(
            "yarn_attribute_ids",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("yarns", "yarn_attribute_ids")
