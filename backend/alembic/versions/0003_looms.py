"""looms

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "looms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manufacturer", sa.String(255), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("purchase_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("supports_lift_tracking", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("supports_treadle_tracking", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_looms_owner_id", "looms", ["owner_id"])

    op.create_table(
        "loom_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loom_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("num_shafts", sa.Integer, nullable=False),
        sa.Column("num_treadles", sa.Integer, nullable=False),
        sa.Column("weaving_width", sa.Numeric(6, 1), nullable=True),
        sa.Column("weaving_width_unit", sa.String(5), nullable=False, server_default="cm"),
        sa.Column("warp_waste_allowance", sa.Numeric(6, 1), nullable=True),
        sa.Column("warp_waste_unit", sa.String(5), nullable=False, server_default="cm"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["loom_id"], ["looms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loom_versions_loom_id", "loom_versions", ["loom_id"])


def downgrade() -> None:
    op.drop_table("loom_versions")
    op.drop_table("looms")
