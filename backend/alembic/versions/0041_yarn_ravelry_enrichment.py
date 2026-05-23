"""add ravelry enrichment fields to yarns

Revision ID: 0041_yarn_ravelry_enrichment
Revises: 0040_yarn_ravelry_yarn_id
Create Date: 2026-05-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_yarn_ravelry_enrichment"
down_revision = "0040_yarn_ravelry_yarn_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("yarns", sa.Column("ravelry_permalink", sa.String(200), nullable=True))
    op.add_column("yarns", sa.Column("ravelry_discontinued", sa.Boolean, nullable=True))
    op.add_column("yarns", sa.Column("ravelry_machine_washable", sa.Boolean, nullable=True))
    op.add_column("yarns", sa.Column("ravelry_yarn_company_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("yarns", "ravelry_yarn_company_url")
    op.drop_column("yarns", "ravelry_machine_washable")
    op.drop_column("yarns", "ravelry_discontinued")
    op.drop_column("yarns", "ravelry_permalink")
