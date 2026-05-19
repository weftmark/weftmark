"""Seed loom_references from docs/research/looms/loom-data-master.json.

Usage (from repo root):
    docker exec weaving_site_backend python seeds/loom_references.py
    docker exec weftmark-dev_backend python seeds/loom_references.py

Idempotent — upserts on (brand, model_name). Safe to re-run after the JSON
is updated to add new entries or correct existing ones.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Fields that exist in the JSON data but are NOT stored in the DB (metadata only).
_SKIP_FIELDS = {"_brand", "_model", "_confidence", "_flags", "_verified_by", "_source_notes"}

# Mapping from research JSON field names to DB column names where they differ.
_FIELD_MAP: dict[str, str] = {}  # currently identical; kept for future divergence

# JSON fields whose values are lists (stored as JSONB arrays).
_ARRAY_FIELDS = {
    "shaft_count_options",
    "treadle_count",
    "weaving_width_options_inches",
    "weaving_width_options_cm",
    "reed_dent_included",
    "compatible_software",
}

# All DB columns on loom_references (excluding id / timestamps).
_DB_COLUMNS = {
    "brand",
    "model_name",
    "model_series",
    "loom_category",
    "shedding_mechanism",
    "shaft_count_options",
    "treadle_count",
    "weaving_width_options_inches",
    "weaving_width_options_cm",
    "frame_material",
    "foldable",
    "foldable_while_warped",
    "weight_lbs",
    "unfolded_depth_inches",
    "folded_depth_inches",
    "castle_height_inches",
    "breast_beam_height_inches",
    "reed_included",
    "reed_dent_included",
    "reed_material",
    "heddle_type",
    "heddles_per_shaft_included",
    "brake_type",
    "beater_type",
    "beater_adjustable",
    "tie_up_system",
    "treadle_hinge",
    "shaft_upgrade_available",
    "max_shafts_with_upgrade",
    "four_now_four_later",
    "height_extender_available",
    "height_extender_inches",
    "sectional_beam_available",
    "double_back_beam_available",
    "floating_breast_beam",
    "fly_shuttle_available",
    "mobility_wheels_included",
    "stroller_available",
    "shaft_switching_device_available",
    "lease_sticks_included",
    "raddle_included",
    "shuttle_included",
    "carry_bag_included",
    "assembly_required",
    "finish_required",
    "origin_country",
    "warranty_years",
    "dobby_type",
    "compatible_software",
}


def _locate_json() -> Path:
    """Find loom-data-master.json regardless of where the script is invoked from."""
    candidates = [
        # Bundled alongside the seed script inside the Docker image (primary)
        Path(__file__).parent / "loom-data-master.json",
        # Repo root — local dev running outside the container
        Path(__file__).parent.parent.parent / "docs" / "research" / "looms" / "loom-data-master.json",
        Path("docs/research/looms/loom-data-master.json"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("Could not find loom-data-master.json. Run from the repo root or inside the container.")


def _coerce_entry(raw: dict) -> dict:
    """Convert a raw JSON entry to a dict of DB column values."""
    row: dict = {}
    for json_key, value in raw.items():
        if json_key in _SKIP_FIELDS:
            continue
        col = _FIELD_MAP.get(json_key, json_key)
        if col not in _DB_COLUMNS:
            continue
        # Array fields: must be a list of numbers; filter out strings and empty lists
        if col in _ARRAY_FIELDS:
            if not isinstance(value, list):
                value = None
            else:
                value = [v for v in value if isinstance(v, (int, float))]
                if not value:
                    value = None
        elif isinstance(value, (dict, list)):
            # Scalar column received a non-scalar — skip it
            value = None
        row[col] = value
    return row


async def seed() -> None:
    # Import here so this script can be run stand-alone in the container
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    raw_dsn = os.environ.get("POSTGRES_DSN", "")
    if not raw_dsn:
        # Fall back to individual vars (local dev)
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5433")
        db_name = os.environ.get("POSTGRES_DB", "weaving_site")
        user = os.environ.get("POSTGRES_USER", "postgres")
        pw = os.environ.get("POSTGRES_PASSWORD", "")
        raw_dsn = f"postgresql://{user}:{pw}@{host}:{port}/{db_name}"

    dsn = raw_dsn.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://"
    )

    engine = create_async_engine(dsn, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    json_path = _locate_json()
    with json_path.open() as f:
        data = json.load(f)

    if isinstance(data, dict) and "looms" in data:
        entries = data["looms"]
    elif isinstance(data, list):
        entries = data
    else:
        raise ValueError("Unexpected JSON structure — expected a list or {looms: [...]}")

    inserted = updated = skipped = 0

    async with Session() as session:
        async with session.begin():
            for raw in entries:
                row = _coerce_entry(raw)
                brand = row.get("brand", "").strip()
                model = row.get("model_name", "").strip()
                if not brand or not model:
                    log.warning("Skipping entry with missing brand/model: %s", raw.get("_model"))
                    skipped += 1
                    continue

                existing = await session.scalar(
                    text(
                        "SELECT id FROM loom_references "
                        "WHERE lower(brand) = lower(:brand) AND lower(model_name) = lower(:model)"
                    ).bindparams(brand=brand, model=model)
                )

                # Serialize params (lists → JSON strings for JSONB columns)
                params = {k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()}

                if existing:
                    # Use CAST syntax so SQLAlchemy's text() parser sees clean :name tokens
                    set_clauses = ", ".join(
                        f"{col} = cast(:{col} as jsonb)" if col in _ARRAY_FIELDS else f"{col} = :{col}"
                        for col in row
                        if col not in ("brand", "model_name")
                    )
                    if set_clauses:
                        await session.execute(
                            text(
                                f"UPDATE loom_references SET {set_clauses}, updated_at = now() "
                                f"WHERE lower(brand) = lower(:brand) AND lower(model_name) = lower(:model)"
                            ),
                            {**params, "brand": brand, "model": model},
                        )
                    updated += 1
                else:
                    row["id"] = str(uuid.uuid4())
                    params["id"] = row["id"]
                    cols = ", ".join(row.keys())
                    vals = ", ".join(f"cast(:{k} as jsonb)" if k in _ARRAY_FIELDS else f":{k}" for k in row.keys())
                    await session.execute(
                        text(f"INSERT INTO loom_references ({cols}) VALUES ({vals})"),
                        params,
                    )
                    inserted += 1

    await engine.dispose()
    print(f"Seed complete: {inserted} inserted, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(seed())
