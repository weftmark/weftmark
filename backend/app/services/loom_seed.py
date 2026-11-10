"""Core loom_references seeding logic.

Called by app.tasks.seeds (Celery task) and by seeds/loom_references.py (CLI).
Uses app.config.get_settings() for the database URL so it works in the Celery
worker process without any sys.path manipulation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

_SKIP_FIELDS = {"_brand", "_model", "_confidence", "_flags", "_verified_by", "_source_notes"}
_FIELD_MAP: dict[str, str] = {}

_ARRAY_FIELDS = {
    "shaft_count_options",
    "treadle_count",
    "weaving_width_options_inches",
    "weaving_width_options_cm",
    "reed_dent_included",
    "compatible_software",
}

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


def locate_json() -> Path:
    """Find loom-data-master.json from any invocation context."""
    _here = Path(__file__).parent  # app/services/
    candidates = [
        _here.parent.parent / "seeds" / "loom-data-master.json",  # container: /app/seeds/
        _here.parent.parent.parent.parent / "docs" / "research" / "looms" / "loom-data-master.json",  # local dev
        Path("docs/research/looms/loom-data-master.json"),  # CWD fallback
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("Could not find loom-data-master.json. Run from the repo root or inside the container.")


def _read_json(path: Path) -> dict | list:
    with path.open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def _coerce_array(value: object) -> list | None:
    if not isinstance(value, list):
        return None
    numeric = [v for v in value if isinstance(v, (int, float))]
    return numeric or None


def _coerce_entry(raw: dict) -> dict:
    row: dict = {}
    for json_key, value in raw.items():
        if json_key in _SKIP_FIELDS:
            continue
        col = _FIELD_MAP.get(json_key, json_key)
        if col not in _DB_COLUMNS:
            continue
        if col in _ARRAY_FIELDS:
            value = _coerce_array(value)
        elif isinstance(value, (dict, list)):
            value = None
        row[col] = value
    return row


def _extract_entries(data: dict | list) -> list[dict]:
    if isinstance(data, dict) and "looms" in data:
        return data["looms"]  # type: ignore[no-any-return]
    if isinstance(data, list):
        return data
    raise ValueError("Unexpected JSON structure — expected a list or {looms: [...]}")


async def _upsert_row(session, raw: dict) -> str:
    """Coerce and upsert a single loom-reference row. Returns 'inserted', 'updated', or 'skipped'."""
    from sqlalchemy import text

    row = _coerce_entry(raw)
    brand = row.get("brand", "").strip()
    model = row.get("model_name", "").strip()
    if not brand or not model:
        log.warning("Skipping entry with missing brand/model: %s", raw.get("_model"))
        return "skipped"

    existing = await session.scalar(
        text(
            "SELECT id FROM loom_references WHERE lower(brand) = lower(:brand) AND lower(model_name) = lower(:model)"
        ).bindparams(brand=brand, model=model)
    )

    params = {k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()}

    if existing:
        set_clauses = ", ".join(
            f"{col} = cast(:{col} as jsonb)" if col in _ARRAY_FIELDS else f"{col} = :{col}"
            for col in row
            if col not in ("brand", "model_name")
        )
        if set_clauses:
            await session.execute(
                text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text  # noqa: E501
                    f"UPDATE loom_references SET {set_clauses}, updated_at = now() "  # nosec B608
                    f"WHERE lower(brand) = lower(:brand) AND lower(model_name) = lower(:model)"
                ),
                {**params, "brand": brand, "model": model},
            )
        return "updated"

    row["id"] = str(uuid.uuid4())
    params["id"] = row["id"]
    cols = ", ".join(row.keys())
    vals = ", ".join(f"cast(:{k} as jsonb)" if k in _ARRAY_FIELDS else f":{k}" for k in row.keys())
    await session.execute(
        text(f"INSERT INTO loom_references ({cols}) VALUES ({vals})"),  # nosec B608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        params,
    )
    return "inserted"


async def seed() -> dict:
    """Upsert loom_references from loom-data-master.json. Returns insert/update/skip counts."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    json_path = locate_json()
    data = await asyncio.to_thread(_read_json, json_path)
    entries = _extract_entries(data)

    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    async with session_factory() as session:
        async with session.begin():
            for raw in entries:
                outcome = await _upsert_row(session, raw)
                counts[outcome] += 1

    await engine.dispose()
    log.info("loom_seed inserted=%d updated=%d skipped=%d", counts["inserted"], counts["updated"], counts["skipped"])
    return counts
