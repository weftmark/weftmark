import mimetypes
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.yarn import Yarn, Skein, SKEIN_STATUSES
from app.models.user import User
from app.services import storage

router = APIRouter(prefix="/api/yarn", tags=["yarn"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

SkeinStatus = Literal["available", "in_use", "consumed"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SkeinSchema(BaseModel):
    id: uuid.UUID
    status: str
    current_yardage: Decimal | None
    current_weight_oz: Decimal | None
    current_weight_g: Decimal | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class YarnSummary(BaseModel):
    id: uuid.UUID
    brand: str
    name: str
    weight_notation: str | None
    weight_category: str | None
    fiber_content: str | None
    color_name: str | None
    color_hex: str | None
    unit_yardage: Decimal | None
    has_photo: bool
    skein_count: int
    available_count: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_yarn(cls, yarn: Yarn) -> "YarnSummary":
        return cls.model_validate({
            "id": yarn.id,
            "brand": yarn.brand,
            "name": yarn.name,
            "weight_notation": yarn.weight_notation,
            "weight_category": yarn.weight_category,
            "fiber_content": yarn.fiber_content,
            "color_name": yarn.color_name,
            "color_hex": yarn.color_hex,
            "unit_yardage": yarn.unit_yardage,
            "has_photo": yarn.photo_path is not None,
            "skein_count": len(yarn.skeins),
            "available_count": sum(1 for s in yarn.skeins if s.status == "available"),
            "created_at": yarn.created_at,
        })


class YarnDetail(YarnSummary):
    unit_weight_oz: Decimal | None
    unit_weight_g: Decimal | None
    yards_per_pound: Decimal | None
    sett_min: int | None
    sett_max: int | None
    purchase_source: str | None
    purchase_price: Decimal | None
    purchase_date: date | None
    notes: str | None
    skeins: list[SkeinSchema]

    @classmethod
    def from_yarn(cls, yarn: Yarn) -> "YarnDetail":  # type: ignore[override]
        return cls.model_validate({
            "id": yarn.id,
            "brand": yarn.brand,
            "name": yarn.name,
            "weight_notation": yarn.weight_notation,
            "weight_category": yarn.weight_category,
            "fiber_content": yarn.fiber_content,
            "color_name": yarn.color_name,
            "color_hex": yarn.color_hex,
            "unit_yardage": yarn.unit_yardage,
            "unit_weight_oz": yarn.unit_weight_oz,
            "unit_weight_g": yarn.unit_weight_g,
            "yards_per_pound": yarn.yards_per_pound,
            "sett_min": yarn.sett_min,
            "sett_max": yarn.sett_max,
            "purchase_source": yarn.purchase_source,
            "purchase_price": yarn.purchase_price,
            "purchase_date": yarn.purchase_date,
            "notes": yarn.notes,
            "has_photo": yarn.photo_path is not None,
            "skein_count": len(yarn.skeins),
            "available_count": sum(1 for s in yarn.skeins if s.status == "available"),
            "skeins": yarn.skeins,
            "created_at": yarn.created_at,
        })


class CreateYarnRequest(BaseModel):
    brand: str
    name: str
    weight_notation: str | None = None
    weight_category: str | None = None
    fiber_content: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    unit_weight_oz: Decimal | None = None
    unit_weight_g: Decimal | None = None
    unit_yardage: Decimal | None = None
    yards_per_pound: Decimal | None = None
    sett_min: int | None = None
    sett_max: int | None = None
    purchase_source: str | None = None
    purchase_price: Decimal | None = None
    purchase_date: date | None = None
    notes: str | None = None


class UpdateYarnRequest(BaseModel):
    brand: str | None = None
    name: str | None = None
    weight_notation: str | None = None
    weight_category: str | None = None
    fiber_content: str | None = None
    color_name: str | None = None
    color_hex: str | None = None
    unit_weight_oz: Decimal | None = None
    unit_weight_g: Decimal | None = None
    unit_yardage: Decimal | None = None
    yards_per_pound: Decimal | None = None
    sett_min: int | None = None
    sett_max: int | None = None
    purchase_source: str | None = None
    purchase_price: Decimal | None = None
    purchase_date: date | None = None
    notes: str | None = None


class CloneYarnRequest(BaseModel):
    color_name: str | None = None
    color_hex: str | None = None


class AddSkeinsRequest(BaseModel):
    quantity: int = 1
    status: SkeinStatus = "available"
    current_yardage: Decimal | None = None
    current_weight_oz: Decimal | None = None
    current_weight_g: Decimal | None = None
    notes: str | None = None


class UpdateSkeinRequest(BaseModel):
    status: SkeinStatus | None = None
    current_yardage: Decimal | None = None
    current_weight_oz: Decimal | None = None
    current_weight_g: Decimal | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_yarn(yarn_id: uuid.UUID, user: User, db: AsyncSession) -> Yarn:
    yarn = await db.scalar(
        select(Yarn)
        .where(Yarn.id == yarn_id, Yarn.owner_id == user.id, Yarn.deleted_at.is_(None))
        .options(selectinload(Yarn.skeins))
    )
    if yarn is None:
        raise HTTPException(status_code=404, detail="Yarn not found")
    return yarn


async def _get_owned_skein(
    yarn_id: uuid.UUID, skein_id: uuid.UUID, user: User, db: AsyncSession
) -> tuple[Yarn, Skein]:
    yarn = await _get_owned_yarn(yarn_id, user, db)
    skein = next((s for s in yarn.skeins if s.id == skein_id), None)
    if skein is None:
        raise HTTPException(status_code=404, detail="Skein not found")
    return yarn, skein


def _validate_image(file: UploadFile) -> None:
    ct = file.content_type or ""
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {ct}. Use JPEG, PNG, WebP, or GIF.")


def _ext(content_type: str) -> str:
    return mimetypes.guess_extension(content_type) or ""


# ---------------------------------------------------------------------------
# Yarn CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=YarnDetail, status_code=201)
async def create_yarn(
    body: CreateYarnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YarnDetail:
    yarn = Yarn(owner_id=current_user.id, **body.model_dump())
    db.add(yarn)
    await db.commit()
    yarn = await _get_owned_yarn(yarn.id, current_user, db)
    return YarnDetail.from_yarn(yarn)


@router.get("", response_model=list[YarnSummary])
async def list_yarn(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[YarnSummary]:
    result = await db.scalars(
        select(Yarn)
        .where(Yarn.owner_id == current_user.id, Yarn.deleted_at.is_(None))
        .options(selectinload(Yarn.skeins))
        .order_by(Yarn.brand, Yarn.name)
    )
    return [YarnSummary.from_yarn(y) for y in result.all()]


@router.get("/{yarn_id}", response_model=YarnDetail)
async def get_yarn(
    yarn_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YarnDetail:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    return YarnDetail.from_yarn(yarn)


@router.patch("/{yarn_id}", response_model=YarnDetail)
async def update_yarn(
    yarn_id: uuid.UUID,
    body: UpdateYarnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YarnDetail:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(yarn, field, value)
    await db.commit()
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    return YarnDetail.from_yarn(yarn)


@router.delete("/{yarn_id}", status_code=204)
async def delete_yarn(
    yarn_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    yarn.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Yarn photo
# ---------------------------------------------------------------------------

@router.put("/{yarn_id}/photo", status_code=204)
async def upload_yarn_photo(
    yarn_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _validate_image(file)
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    if yarn.photo_path:
        storage.delete_yarn_photo(yarn.photo_path)
    ext = _ext(file.content_type or "")
    yarn.photo_path = storage.save_yarn_photo(yarn_id, ext, data)
    await db.commit()


@router.get("/{yarn_id}/photo")
async def get_yarn_photo(
    yarn_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    if not yarn.photo_path or not storage.file_exists(yarn.photo_path):
        raise HTTPException(status_code=404, detail="No photo")
    data = storage.read_file(yarn.photo_path)
    ct = mimetypes.guess_type(yarn.photo_path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ct)


@router.delete("/{yarn_id}/photo", status_code=204)
async def delete_yarn_photo(
    yarn_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    if yarn.photo_path:
        storage.delete_yarn_photo(yarn.photo_path)
        yarn.photo_path = None
        await db.commit()


# ---------------------------------------------------------------------------
# Skeins
# ---------------------------------------------------------------------------

@router.post("/{yarn_id}/skeins", response_model=list[SkeinSchema], status_code=201)
async def add_skeins(
    yarn_id: uuid.UUID,
    body: AddSkeinsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkeinSchema]:
    yarn = await _get_owned_yarn(yarn_id, current_user, db)
    if body.quantity < 1 or body.quantity > 100:
        raise HTTPException(status_code=400, detail="Quantity must be between 1 and 100")
    new_skeins = [
        Skein(
            yarn_id=yarn.id,
            status=body.status,
            current_yardage=body.current_yardage,
            current_weight_oz=body.current_weight_oz,
            current_weight_g=body.current_weight_g,
            notes=body.notes,
        )
        for _ in range(body.quantity)
    ]
    for s in new_skeins:
        db.add(s)
    await db.commit()
    for s in new_skeins:
        await db.refresh(s)
    return [SkeinSchema.model_validate(s) for s in new_skeins]


@router.patch("/{yarn_id}/skeins/{skein_id}", response_model=SkeinSchema)
async def update_skein(
    yarn_id: uuid.UUID,
    skein_id: uuid.UUID,
    body: UpdateSkeinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkeinSchema:
    yarn, skein = await _get_owned_skein(yarn_id, skein_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(skein, field, value)
    await db.commit()
    await db.refresh(skein)
    return SkeinSchema.model_validate(skein)


@router.delete("/{yarn_id}/skeins/{skein_id}", status_code=204)
async def delete_skein(
    yarn_id: uuid.UUID,
    skein_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    yarn, skein = await _get_owned_skein(yarn_id, skein_id, current_user, db)
    await db.delete(skein)
    await db.commit()


# ---------------------------------------------------------------------------
# Clone yarn definition
# ---------------------------------------------------------------------------

@router.post("/{yarn_id}/clone", response_model=YarnDetail, status_code=201)
async def clone_yarn(
    yarn_id: uuid.UUID,
    body: CloneYarnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YarnDetail:
    source = await _get_owned_yarn(yarn_id, current_user, db)
    clone = Yarn(
        owner_id=current_user.id,
        brand=source.brand,
        name=source.name,
        weight_notation=source.weight_notation,
        weight_category=source.weight_category,
        fiber_content=source.fiber_content,
        color_name=body.color_name if body.color_name is not None else source.color_name,
        color_hex=body.color_hex if body.color_hex is not None else source.color_hex,
        unit_weight_oz=source.unit_weight_oz,
        unit_weight_g=source.unit_weight_g,
        unit_yardage=source.unit_yardage,
        yards_per_pound=source.yards_per_pound,
        sett_min=source.sett_min,
        sett_max=source.sett_max,
        purchase_source=source.purchase_source,
        purchase_price=source.purchase_price,
        purchase_date=source.purchase_date,
        notes=source.notes,
    )
    db.add(clone)
    await db.commit()
    clone = await _get_owned_yarn(clone.id, current_user, db)
    return YarnDetail.from_yarn(clone)
