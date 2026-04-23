"""yarn inventory

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "yarns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("weight_notation", sa.String(20), nullable=True),
        sa.Column("weight_category", sa.String(30), nullable=True),
        sa.Column("fiber_content", sa.String(255), nullable=True),
        sa.Column("color_name", sa.String(255), nullable=True),
        sa.Column("color_hex", sa.String(7), nullable=True),
        sa.Column("unit_weight_oz", sa.Numeric(8, 2), nullable=True),
        sa.Column("unit_weight_g", sa.Numeric(8, 2), nullable=True),
        sa.Column("unit_yardage", sa.Numeric(10, 1), nullable=True),
        sa.Column("yards_per_pound", sa.Numeric(10, 1), nullable=True),
        sa.Column("sett_min", sa.Integer, nullable=True),
        sa.Column("sett_max", sa.Integer, nullable=True),
        sa.Column("purchase_source", sa.String(255), nullable=True),
        sa.Column("purchase_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("photo_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_yarns_owner_id", "yarns", ["owner_id"])

    op.create_table(
        "skeins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("yarn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("current_yardage", sa.Numeric(10, 1), nullable=True),
        sa.Column("current_weight_oz", sa.Numeric(8, 2), nullable=True),
        sa.Column("current_weight_g", sa.Numeric(8, 2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["yarn_id"], ["yarns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skeins_yarn_id", "skeins", ["yarn_id"])


def downgrade() -> None:
    op.drop_table("skeins")
    op.drop_table("yarns")
