"""Public loom catalog and admin CRUD for loom_references."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.models.loom import LoomReference
from app.models.user import User

router = APIRouter(tags=["loom-catalog"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoomReferenceSchema(BaseModel):
    id: uuid.UUID
    brand: str
    model_name: str
    model_series: str | None
    loom_category: str
    shedding_mechanism: str | None
    shaft_count_options: list[int] | None
    treadle_count: list[int] | None
    weaving_width_options_inches: list[float] | None
    weaving_width_options_cm: list[float] | None
    frame_material: str | None
    foldable: bool | None
    foldable_while_warped: bool | None
    weight_lbs: Decimal | None
    unfolded_depth_inches: Decimal | None
    folded_depth_inches: Decimal | None
    castle_height_inches: Decimal | None
    breast_beam_height_inches: Decimal | None
    reed_included: bool | None
    reed_dent_included: list[int] | None
    reed_material: str | None
    heddle_type: str | None
    heddles_per_shaft_included: Decimal | None
    brake_type: str | None
    beater_type: str | None
    beater_adjustable: bool | None
    tie_up_system: str | None
    treadle_hinge: str | None
    shaft_upgrade_available: bool | None
    max_shafts_with_upgrade: int | None
    four_now_four_later: bool | None
    height_extender_available: bool | None
    height_extender_inches: Decimal | None
    sectional_beam_available: bool | None
    double_back_beam_available: bool | None
    floating_breast_beam: bool | None
    fly_shuttle_available: bool | None
    mobility_wheels_included: bool | None
    stroller_available: bool | None
    shaft_switching_device_available: bool | None
    lease_sticks_included: bool | None
    raddle_included: bool | None
    shuttle_included: bool | None
    carry_bag_included: bool | None
    assembly_required: bool | None
    finish_required: bool | None
    origin_country: str | None
    warranty_years: Decimal | None
    dobby_type: str | None
    compatible_software: list[str] | None

    model_config = {"from_attributes": True}


class LoomReferenceSummary(BaseModel):
    id: uuid.UUID
    brand: str
    model_name: str
    model_series: str | None
    loom_category: str
    shedding_mechanism: str | None
    shaft_count_options: list[int] | None
    treadle_count: list[int] | None
    weaving_width_options_inches: list[float] | None
    weaving_width_options_cm: list[float] | None
    foldable: bool | None
    origin_country: str | None

    model_config = {"from_attributes": True}


class CreateLoomReferenceRequest(BaseModel):
    brand: str
    model_name: str
    model_series: str | None = None
    loom_category: str
    shedding_mechanism: str | None = None
    shaft_count_options: list[int] | None = None
    treadle_count: list[int] | None = None
    weaving_width_options_inches: list[float] | None = None
    weaving_width_options_cm: list[float] | None = None
    frame_material: str | None = None
    foldable: bool | None = None
    foldable_while_warped: bool | None = None
    weight_lbs: Decimal | None = None
    unfolded_depth_inches: Decimal | None = None
    folded_depth_inches: Decimal | None = None
    castle_height_inches: Decimal | None = None
    breast_beam_height_inches: Decimal | None = None
    reed_included: bool | None = None
    reed_dent_included: list[int] | None = None
    reed_material: str | None = None
    heddle_type: str | None = None
    heddles_per_shaft_included: Decimal | None = None
    brake_type: str | None = None
    beater_type: str | None = None
    beater_adjustable: bool | None = None
    tie_up_system: str | None = None
    treadle_hinge: str | None = None
    shaft_upgrade_available: bool | None = None
    max_shafts_with_upgrade: int | None = None
    four_now_four_later: bool | None = None
    height_extender_available: bool | None = None
    height_extender_inches: Decimal | None = None
    sectional_beam_available: bool | None = None
    double_back_beam_available: bool | None = None
    floating_breast_beam: bool | None = None
    fly_shuttle_available: bool | None = None
    mobility_wheels_included: bool | None = None
    stroller_available: bool | None = None
    shaft_switching_device_available: bool | None = None
    lease_sticks_included: bool | None = None
    raddle_included: bool | None = None
    shuttle_included: bool | None = None
    carry_bag_included: bool | None = None
    assembly_required: bool | None = None
    finish_required: bool | None = None
    origin_country: str | None = None
    warranty_years: Decimal | None = None
    dobby_type: str | None = None
    compatible_software: list[str] | None = None


class UpdateLoomReferenceRequest(BaseModel):
    brand: str | None = None
    model_name: str | None = None
    model_series: str | None = None
    loom_category: str | None = None
    shedding_mechanism: str | None = None
    shaft_count_options: list[int] | None = None
    treadle_count: list[int] | None = None
    weaving_width_options_inches: list[float] | None = None
    weaving_width_options_cm: list[float] | None = None
    frame_material: str | None = None
    foldable: bool | None = None
    foldable_while_warped: bool | None = None
    weight_lbs: Decimal | None = None
    unfolded_depth_inches: Decimal | None = None
    folded_depth_inches: Decimal | None = None
    castle_height_inches: Decimal | None = None
    breast_beam_height_inches: Decimal | None = None
    reed_included: bool | None = None
    reed_dent_included: list[int] | None = None
    reed_material: str | None = None
    heddle_type: str | None = None
    heddles_per_shaft_included: Decimal | None = None
    brake_type: str | None = None
    beater_type: str | None = None
    beater_adjustable: bool | None = None
    tie_up_system: str | None = None
    treadle_hinge: str | None = None
    shaft_upgrade_available: bool | None = None
    max_shafts_with_upgrade: int | None = None
    four_now_four_later: bool | None = None
    height_extender_available: bool | None = None
    height_extender_inches: Decimal | None = None
    sectional_beam_available: bool | None = None
    double_back_beam_available: bool | None = None
    floating_breast_beam: bool | None = None
    fly_shuttle_available: bool | None = None
    mobility_wheels_included: bool | None = None
    stroller_available: bool | None = None
    shaft_switching_device_available: bool | None = None
    lease_sticks_included: bool | None = None
    raddle_included: bool | None = None
    shuttle_included: bool | None = None
    carry_bag_included: bool | None = None
    assembly_required: bool | None = None
    finish_required: bool | None = None
    origin_country: str | None = None
    warranty_years: Decimal | None = None
    dobby_type: str | None = None
    compatible_software: list[str] | None = None


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/api/loom-catalog", tags=["loom-catalog"])


@public_router.get("", response_model=list[LoomReferenceSummary])
async def list_loom_catalog(
    q: str | None = Query(None, description="Search brand, model, or series"),
    category: str | None = Query(None),
    min_shafts: int | None = Query(None),
    foldable: bool | None = Query(None),
    origin_country: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[LoomReferenceSummary]:
    stmt = select(LoomReference).order_by(LoomReference.brand, LoomReference.model_name)

    if q:
        stmt = stmt.where(
            or_(
                func.lower(LoomReference.brand).contains(q.lower()),
                func.lower(LoomReference.model_name).contains(q.lower()),
                func.lower(func.coalesce(LoomReference.model_series, "")).contains(q.lower()),
            )
        )
    if category:
        stmt = stmt.where(LoomReference.loom_category == category)
    if foldable is not None:
        stmt = stmt.where(LoomReference.foldable == foldable)
    if origin_country:
        stmt = stmt.where(func.lower(LoomReference.origin_country) == origin_country.lower())

    rows = await db.scalars(stmt)
    results = list(rows.all())

    # Filter by min_shafts in Python (JSONB array containment)
    if min_shafts is not None:
        results = [r for r in results if r.shaft_count_options and any(s >= min_shafts for s in r.shaft_count_options)]

    return [LoomReferenceSummary.model_validate(r) for r in results]


@public_router.get("/search", response_model=list[LoomReferenceSummary])
async def search_loom_catalog(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[LoomReferenceSummary]:
    """Typeahead search — returns summaries matching brand or model name."""
    ql = q.lower()
    stmt = (
        select(LoomReference)
        .where(
            or_(
                func.lower(LoomReference.brand).contains(ql),
                func.lower(LoomReference.model_name).contains(ql),
                func.lower(func.coalesce(LoomReference.model_series, "")).contains(ql),
            )
        )
        .order_by(LoomReference.brand, LoomReference.model_name)
        .limit(limit)
    )
    rows = await db.scalars(stmt)
    return [LoomReferenceSummary.model_validate(r) for r in rows.all()]


@public_router.get("/{ref_id}", response_model=LoomReferenceSchema)
async def get_loom_reference(
    ref_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> LoomReferenceSchema:
    ref = await db.get(LoomReference, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Loom reference not found")
    return LoomReferenceSchema.model_validate(ref)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

admin_catalog_router = APIRouter(prefix="/api/admin/loom-catalog", tags=["admin"])


@admin_catalog_router.get("", response_model=list[LoomReferenceSchema])
async def admin_list_loom_catalog(
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[LoomReferenceSchema]:
    stmt = select(LoomReference).order_by(LoomReference.brand, LoomReference.model_name)
    if q:
        ql = q.lower()
        stmt = stmt.where(
            or_(
                func.lower(LoomReference.brand).contains(ql),
                func.lower(LoomReference.model_name).contains(ql),
            )
        )
    rows = await db.scalars(stmt)
    return [LoomReferenceSchema.model_validate(r) for r in rows.all()]


@admin_catalog_router.post("", response_model=LoomReferenceSchema, status_code=201)
async def admin_create_loom_reference(
    body: CreateLoomReferenceRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> LoomReferenceSchema:
    existing = await db.scalar(
        select(LoomReference).where(
            func.lower(LoomReference.brand) == body.brand.lower(),
            func.lower(LoomReference.model_name) == body.model_name.lower(),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="A loom reference with this brand and model already exists")
    ref = LoomReference(**body.model_dump())
    db.add(ref)
    await db.commit()
    await db.refresh(ref)
    return LoomReferenceSchema.model_validate(ref)


@admin_catalog_router.patch("/{ref_id}", response_model=LoomReferenceSchema)
async def admin_update_loom_reference(
    ref_id: uuid.UUID,
    body: UpdateLoomReferenceRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> LoomReferenceSchema:
    ref = await db.get(LoomReference, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Loom reference not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(ref, field, value)
    await db.commit()
    await db.refresh(ref)
    return LoomReferenceSchema.model_validate(ref)


@admin_catalog_router.delete("/{ref_id}", status_code=204)
async def admin_delete_loom_reference(
    ref_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    ref = await db.get(LoomReference, ref_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="Loom reference not found")
    # Nullify FK on any linked user looms (cascade SET NULL handles DB side,
    # but explicit check lets us warn callers if needed)
    await db.delete(ref)
    await db.commit()
