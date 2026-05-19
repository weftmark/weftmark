"""loom_references table, loom_reference_id FK on looms, extend loom_type enum

Revision ID: 7d8e9f0a1b2c
Revises: 6c7d8e9f0a1b
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "7d8e9f0a1b2c"
down_revision: str = "6c7d8e9f0a1b"


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Extend loom_type values on existing looms rows                   #
    #    (column is VARCHAR — no Postgres enum to alter, just data)       #
    # ------------------------------------------------------------------ #
    op.execute("UPDATE looms SET loom_type = 'dobby_floor_loom' WHERE loom_type = 'dobby'")

    # ------------------------------------------------------------------ #
    # 2. Create loom_references catalog table                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "loom_references",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Core identity
        sa.Column("brand", sa.String(255), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_series", sa.String(255), nullable=True),
        sa.Column("loom_category", sa.String(50), nullable=False),
        sa.Column("shedding_mechanism", sa.String(50), nullable=True),
        # Configuration arrays
        sa.Column("shaft_count_options", JSONB, nullable=True),
        sa.Column("treadle_count", JSONB, nullable=True),
        sa.Column("weaving_width_options_inches", JSONB, nullable=True),
        sa.Column("weaving_width_options_cm", JSONB, nullable=True),
        # Physical
        sa.Column("frame_material", sa.String(50), nullable=True),
        sa.Column("foldable", sa.Boolean, nullable=True),
        sa.Column("foldable_while_warped", sa.Boolean, nullable=True),
        sa.Column("weight_lbs", sa.Numeric(8, 2), nullable=True),
        sa.Column("unfolded_depth_inches", sa.Numeric(8, 2), nullable=True),
        sa.Column("folded_depth_inches", sa.Numeric(8, 2), nullable=True),
        sa.Column("castle_height_inches", sa.Numeric(8, 2), nullable=True),
        sa.Column("breast_beam_height_inches", sa.Numeric(8, 2), nullable=True),
        # Reed / heddle
        sa.Column("reed_included", sa.Boolean, nullable=True),
        sa.Column("reed_dent_included", JSONB, nullable=True),
        sa.Column("reed_material", sa.String(50), nullable=True),
        sa.Column("heddle_type", sa.String(50), nullable=True),
        sa.Column("heddles_per_shaft_included", sa.Numeric(8, 1), nullable=True),
        # Beater / brake / tie-up
        sa.Column("brake_type", sa.String(50), nullable=True),
        sa.Column("beater_type", sa.String(50), nullable=True),
        sa.Column("beater_adjustable", sa.Boolean, nullable=True),
        sa.Column("tie_up_system", sa.String(50), nullable=True),
        sa.Column("treadle_hinge", sa.String(50), nullable=True),
        # Upgrades / accessories
        sa.Column("shaft_upgrade_available", sa.Boolean, nullable=True),
        sa.Column("max_shafts_with_upgrade", sa.Integer, nullable=True),
        sa.Column("four_now_four_later", sa.Boolean, nullable=True),
        sa.Column("height_extender_available", sa.Boolean, nullable=True),
        sa.Column("height_extender_inches", sa.Numeric(6, 2), nullable=True),
        sa.Column("sectional_beam_available", sa.Boolean, nullable=True),
        sa.Column("double_back_beam_available", sa.Boolean, nullable=True),
        sa.Column("floating_breast_beam", sa.Boolean, nullable=True),
        sa.Column("fly_shuttle_available", sa.Boolean, nullable=True),
        sa.Column("mobility_wheels_included", sa.Boolean, nullable=True),
        sa.Column("stroller_available", sa.Boolean, nullable=True),
        sa.Column("shaft_switching_device_available", sa.Boolean, nullable=True),
        # Included accessories
        sa.Column("lease_sticks_included", sa.Boolean, nullable=True),
        sa.Column("raddle_included", sa.Boolean, nullable=True),
        sa.Column("shuttle_included", sa.Boolean, nullable=True),
        sa.Column("carry_bag_included", sa.Boolean, nullable=True),
        # Assembly / finish
        sa.Column("assembly_required", sa.Boolean, nullable=True),
        sa.Column("finish_required", sa.Boolean, nullable=True),
        # Origin / warranty
        sa.Column("origin_country", sa.String(100), nullable=True),
        sa.Column("warranty_years", sa.Numeric(5, 1), nullable=True),
        # Dobby-specific
        sa.Column("dobby_type", sa.String(50), nullable=True),
        sa.Column("compatible_software", JSONB, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_loom_references_brand", "loom_references", ["brand"])
    op.create_index("ix_loom_references_model_name", "loom_references", ["model_name"])
    op.create_index("ix_loom_references_loom_category", "loom_references", ["loom_category"])
    op.create_index(
        "ix_loom_references_brand_model",
        "loom_references",
        ["brand", "model_name"],
        unique=True,
    )

    # ------------------------------------------------------------------ #
    # 3. Add loom_reference_id FK to looms                               #
    # ------------------------------------------------------------------ #
    op.add_column(
        "looms",
        sa.Column("loom_reference_id", UUID(as_uuid=True), nullable=True),
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


def downgrade() -> None:
    op.drop_index("ix_looms_loom_reference_id", "looms")
    op.drop_constraint("fk_looms_loom_reference_id", "looms", type_="foreignkey")
    op.drop_column("looms", "loom_reference_id")

    op.drop_index("ix_loom_references_brand_model", "loom_references")
    op.drop_index("ix_loom_references_loom_category", "loom_references")
    op.drop_index("ix_loom_references_model_name", "loom_references")
    op.drop_index("ix_loom_references_brand", "loom_references")
    op.drop_table("loom_references")

    op.execute("UPDATE looms SET loom_type = 'dobby' WHERE loom_type = 'dobby_floor_loom'")
