import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.loom import Loom, LoomVersion, LOOM_TYPES
from app.models.user import User

router = APIRouter(prefix="/api/looms", tags=["looms"])

LoomType = Literal["floor_loom", "table_loom", "rigid_heddle", "inkle", "other"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoomVersionSchema(BaseModel):
    id: uuid.UUID
    version_number: int
    effective_date: date
    description: str | None
    num_shafts: int | None
    num_treadles: int | None
    num_heddles: int | None
    weaving_width: Decimal | None
    weaving_width_unit: str
    warp_waste_allowance: Decimal | None
    warp_waste_unit: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoomSummary(BaseModel):
    id: uuid.UUID
    loom_type: str
    manufacturer: str
    model_name: str
    serial_number: str | None
    supports_lift_tracking: bool
    supports_treadle_tracking: bool
    notes: str | None
    current_version: LoomVersionSchema | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoomDetail(LoomSummary):
    purchase_date: date | None
    purchase_price: Decimal | None
    vendor: str | None
    versions: list[LoomVersionSchema]


class CreateLoomRequest(BaseModel):
    loom_type: LoomType = "floor_loom"
    manufacturer: str
    model_name: str
    serial_number: str | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = None
    vendor: str | None = None
    supports_lift_tracking: bool = False
    supports_treadle_tracking: bool = False
    notes: str | None = None
    # Initial version
    effective_date: date
    num_shafts: int | None = None
    num_treadles: int | None = None
    num_heddles: int | None = None
    weaving_width: Decimal | None = None
    weaving_width_unit: str = "cm"
    warp_waste_allowance: Decimal | None = None
    warp_waste_unit: str = "cm"
    version_description: str | None = None


class UpdateLoomRequest(BaseModel):
    loom_type: LoomType | None = None
    manufacturer: str | None = None
    model_name: str | None = None
    serial_number: str | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = None
    vendor: str | None = None
    supports_lift_tracking: bool | None = None
    supports_treadle_tracking: bool | None = None
    notes: str | None = None


class AddVersionRequest(BaseModel):
    effective_date: date
    description: str | None = None
    num_shafts: int | None = None
    num_treadles: int | None = None
    num_heddles: int | None = None
    weaving_width: Decimal | None = None
    weaving_width_unit: str = "cm"
    warp_waste_allowance: Decimal | None = None
    warp_waste_unit: str = "cm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_loom(loom_id: uuid.UUID, user: User, db: AsyncSession) -> Loom:
    loom = await db.scalar(
        select(Loom)
        .where(Loom.id == loom_id, Loom.owner_id == user.id, Loom.deleted_at.is_(None))
        .options(selectinload(Loom.versions))
    )
    if loom is None:
        raise HTTPException(status_code=404, detail="Loom not found")
    return loom


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=LoomDetail, status_code=201)
async def create_loom(
    body: CreateLoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomDetail:
    loom = Loom(
        owner_id=current_user.id,
        loom_type=body.loom_type,
        manufacturer=body.manufacturer,
        model_name=body.model_name,
        serial_number=body.serial_number,
        purchase_date=body.purchase_date,
        purchase_price=body.purchase_price,
        vendor=body.vendor,
        supports_lift_tracking=body.supports_lift_tracking,
        supports_treadle_tracking=body.supports_treadle_tracking,
        notes=body.notes,
    )
    db.add(loom)
    await db.flush()

    version = LoomVersion(
        loom_id=loom.id,
        version_number=1,
        effective_date=body.effective_date,
        description=body.version_description or "Initial configuration",
        num_shafts=body.num_shafts,
        num_treadles=body.num_treadles,
        num_heddles=body.num_heddles,
        weaving_width=body.weaving_width,
        weaving_width_unit=body.weaving_width_unit,
        warp_waste_allowance=body.warp_waste_allowance,
        warp_waste_unit=body.warp_waste_unit,
    )
    db.add(version)
    await db.commit()

    loom = await _get_owned_loom(loom.id, current_user, db)
    return LoomDetail.model_validate(loom)


@router.get("", response_model=list[LoomSummary])
async def list_looms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LoomSummary]:
    result = await db.scalars(
        select(Loom)
        .where(Loom.owner_id == current_user.id, Loom.deleted_at.is_(None))
        .options(selectinload(Loom.versions))
        .order_by(Loom.created_at.desc())
    )
    return [LoomSummary.model_validate(l) for l in result.all()]


@router.get("/{loom_id}", response_model=LoomDetail)
async def get_loom(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomDetail:
    loom = await _get_owned_loom(loom_id, current_user, db)
    return LoomDetail.model_validate(loom)


@router.patch("/{loom_id}", response_model=LoomDetail)
async def update_loom(
    loom_id: uuid.UUID,
    body: UpdateLoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomDetail:
    loom = await _get_owned_loom(loom_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(loom, field, value)
    await db.commit()
    loom = await _get_owned_loom(loom_id, current_user, db)
    return LoomDetail.model_validate(loom)


@router.post("/{loom_id}/versions", response_model=LoomVersionSchema, status_code=201)
async def add_version(
    loom_id: uuid.UUID,
    body: AddVersionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionSchema:
    loom = await _get_owned_loom(loom_id, current_user, db)
    next_number = max((v.version_number for v in loom.versions), default=0) + 1
    version = LoomVersion(
        loom_id=loom.id,
        version_number=next_number,
        effective_date=body.effective_date,
        description=body.description,
        num_shafts=body.num_shafts,
        num_treadles=body.num_treadles,
        num_heddles=body.num_heddles,
        weaving_width=body.weaving_width,
        weaving_width_unit=body.weaving_width_unit,
        warp_waste_allowance=body.warp_waste_allowance,
        warp_waste_unit=body.warp_waste_unit,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return LoomVersionSchema.model_validate(version)


@router.delete("/{loom_id}", status_code=204)
async def delete_loom(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom = await _get_owned_loom(loom_id, current_user, db)
    loom.soft_delete()
    await db.commit()
