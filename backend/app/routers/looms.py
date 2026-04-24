import mimetypes
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user, get_db
from app.models.loom import (
    Loom,
    LoomVersion,
    LoomVersionAccessory,
    LoomVersionPhoto,
    LoomVersionReceipt,
)
from app.models.user import User
from app.services import storage

router = APIRouter(prefix="/api/looms", tags=["looms"])

LoomType = Literal["floor_loom", "table_loom", "rigid_heddle", "inkle", "other"]

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_VERSION_PHOTOS = 5


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoomVersionPhotoSchema(BaseModel):
    id: uuid.UUID
    filename: str
    display_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LoomVersionReceiptSchema(BaseModel):
    id: uuid.UUID
    filename: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LoomVersionAccessorySchema(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoomVersionSchema(BaseModel):
    id: uuid.UUID
    version_number: int
    name: str | None
    effective_date: date
    description: str | None
    num_shafts: int | None
    num_treadles: int | None
    num_heddles: int | None
    weaving_width: Decimal | None
    weaving_width_unit: str
    warp_waste_allowance: Decimal | None
    warp_waste_unit: str
    photos: list[LoomVersionPhotoSchema]
    receipts: list[LoomVersionReceiptSchema]
    accessories: list[LoomVersionAccessorySchema]
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
    has_photo: bool
    current_version: LoomVersionSchema | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_loom(cls, loom: Loom) -> "LoomSummary":
        data = {
            "id": loom.id,
            "loom_type": loom.loom_type,
            "manufacturer": loom.manufacturer,
            "model_name": loom.model_name,
            "serial_number": loom.serial_number,
            "supports_lift_tracking": loom.supports_lift_tracking,
            "supports_treadle_tracking": loom.supports_treadle_tracking,
            "notes": loom.notes,
            "has_photo": loom.photo_path is not None,
            "current_version": loom.current_version,
            "created_at": loom.created_at,
        }
        return cls.model_validate(data)


class LoomDetail(BaseModel):
    id: uuid.UUID
    loom_type: str
    manufacturer: str
    model_name: str
    serial_number: str | None
    purchase_date: date | None
    purchase_price: Decimal | None
    vendor: str | None
    supports_lift_tracking: bool
    supports_treadle_tracking: bool
    notes: str | None
    has_photo: bool
    current_version: LoomVersionSchema | None
    versions: list[LoomVersionSchema]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_loom(cls, loom: Loom) -> "LoomDetail":
        data = {
            "id": loom.id,
            "loom_type": loom.loom_type,
            "manufacturer": loom.manufacturer,
            "model_name": loom.model_name,
            "serial_number": loom.serial_number,
            "purchase_date": loom.purchase_date,
            "purchase_price": loom.purchase_price,
            "vendor": loom.vendor,
            "supports_lift_tracking": loom.supports_lift_tracking,
            "supports_treadle_tracking": loom.supports_treadle_tracking,
            "notes": loom.notes,
            "has_photo": loom.photo_path is not None,
            "current_version": loom.current_version,
            "versions": loom.versions,
            "created_at": loom.created_at,
        }
        return cls.model_validate(data)


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
    name: str | None = None
    effective_date: date
    description: str | None = None
    num_shafts: int | None = None
    num_treadles: int | None = None
    num_heddles: int | None = None
    weaving_width: Decimal | None = None
    weaving_width_unit: str = "cm"
    warp_waste_allowance: Decimal | None = None
    warp_waste_unit: str = "cm"


class UpdateVersionRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class CloneVersionRequest(BaseModel):
    name: str | None = None
    effective_date: date
    description: str | None = None
    include_accessories: bool = True


class AddAccessoryRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_loom(loom_id: uuid.UUID, user: User, db: AsyncSession) -> Loom:
    loom = await db.scalar(
        select(Loom)
        .where(Loom.id == loom_id, Loom.owner_id == user.id, Loom.deleted_at.is_(None))
        .options(
            selectinload(Loom.versions).selectinload(LoomVersion.photos),
            selectinload(Loom.versions).selectinload(LoomVersion.receipts),
            selectinload(Loom.versions).selectinload(LoomVersion.accessories),
        )
    )
    if loom is None:
        raise HTTPException(status_code=404, detail="Loom not found")
    return loom


async def _get_owned_version(
    loom_id: uuid.UUID, version_id: uuid.UUID, user: User, db: AsyncSession
) -> tuple[Loom, LoomVersion]:
    loom = await _get_owned_loom(loom_id, user, db)
    version = next((v for v in loom.versions if v.id == version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return loom, version


def _validate_image(file: UploadFile) -> None:
    ct = file.content_type or ""
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {ct}. Use JPEG, PNG, WebP, or GIF.")


def _validate_receipt(file: UploadFile) -> None:
    ct = file.content_type or ""
    if ct not in ALLOWED_RECEIPT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ct}. Use JPEG, PNG, WebP, or PDF.")


def _ext(content_type: str) -> str:
    return mimetypes.guess_extension(content_type) or ""


# ---------------------------------------------------------------------------
# Loom CRUD
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
    return LoomDetail.from_loom(loom)


@router.get("", response_model=list[LoomSummary])
async def list_looms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LoomSummary]:
    result = await db.scalars(
        select(Loom)
        .where(Loom.owner_id == current_user.id, Loom.deleted_at.is_(None))
        .options(
            selectinload(Loom.versions).selectinload(LoomVersion.photos),
            selectinload(Loom.versions).selectinload(LoomVersion.receipts),
            selectinload(Loom.versions).selectinload(LoomVersion.accessories),
        )
        .order_by(Loom.created_at.desc())
    )
    return [LoomSummary.from_loom(loom) for loom in result.all()]


@router.get("/{loom_id}", response_model=LoomDetail)
async def get_loom(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomDetail:
    loom = await _get_owned_loom(loom_id, current_user, db)
    return LoomDetail.from_loom(loom)


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
    return LoomDetail.from_loom(loom)


@router.delete("/{loom_id}", status_code=204)
async def delete_loom(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom = await _get_owned_loom(loom_id, current_user, db)
    loom.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Loom profile photo
# ---------------------------------------------------------------------------


@router.put("/{loom_id}/photo", status_code=204)
async def upload_loom_photo(
    loom_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _validate_image(file)
    loom = await _get_owned_loom(loom_id, current_user, db)
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    if loom.photo_path:
        storage.delete_loom_photo(loom.photo_path)
    ext = _ext(file.content_type or "")
    loom.photo_path = storage.save_loom_photo(loom_id, ext, data)
    await db.commit()


@router.delete("/{loom_id}/photo", status_code=204)
async def delete_loom_photo(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom = await _get_owned_loom(loom_id, current_user, db)
    if loom.photo_path:
        storage.delete_loom_photo(loom.photo_path)
        loom.photo_path = None
        await db.commit()


@router.get("/{loom_id}/photo")
async def get_loom_photo(
    loom_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    loom = await _get_owned_loom(loom_id, current_user, db)
    if not loom.photo_path or not storage.file_exists(loom.photo_path):
        raise HTTPException(status_code=404, detail="No photo")
    data = storage.read_file(loom.photo_path)
    ct = mimetypes.guess_type(loom.photo_path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ct)


# ---------------------------------------------------------------------------
# Loom versions
# ---------------------------------------------------------------------------


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
        name=body.name,
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
    await db.refresh(version, ["photos", "receipts", "accessories"])
    return LoomVersionSchema.model_validate(version)


# ---------------------------------------------------------------------------
# Version photos
# ---------------------------------------------------------------------------


@router.post("/{loom_id}/versions/{version_id}/photos", response_model=LoomVersionPhotoSchema, status_code=201)
async def upload_version_photo(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionPhotoSchema:
    _validate_image(file)
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    if len(version.photos) >= MAX_VERSION_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_VERSION_PHOTOS} photos per configuration")
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5 MB)")
    photo_id = uuid.uuid4()
    ext = _ext(file.content_type or "")
    path = storage.save_version_photo(loom_id, version_id, photo_id, ext, data)
    display_order = max((p.display_order for p in version.photos), default=-1) + 1
    photo = LoomVersionPhoto(
        id=photo_id,
        loom_version_id=version_id,
        filename=file.filename or f"{photo_id}{ext}",
        path=path,
        display_order=display_order,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return LoomVersionPhotoSchema.model_validate(photo)


@router.get("/{loom_id}/versions/{version_id}/photos/{photo_id}")
async def get_version_photo(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    photo = next((p for p in version.photos if p.id == photo_id), None)
    if photo is None or not storage.file_exists(photo.path):
        raise HTTPException(status_code=404, detail="Photo not found")
    data = storage.read_file(photo.path)
    ct = mimetypes.guess_type(photo.path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ct)


@router.delete("/{loom_id}/versions/{version_id}/photos/{photo_id}", status_code=204)
async def delete_version_photo(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    photo = next((p for p in version.photos if p.id == photo_id), None)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    storage.delete_version_photo(photo.path)
    await db.delete(photo)
    await db.commit()


# ---------------------------------------------------------------------------
# Version receipts
# ---------------------------------------------------------------------------


@router.post("/{loom_id}/versions/{version_id}/receipts", response_model=LoomVersionReceiptSchema, status_code=201)
async def upload_version_receipt(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    file: UploadFile = File(...),
    description: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionReceiptSchema:
    _validate_receipt(file)
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 20 MB)")
    receipt_id = uuid.uuid4()
    ext = _ext(file.content_type or "")
    path = storage.save_version_receipt(loom_id, version_id, receipt_id, ext, data)
    receipt = LoomVersionReceipt(
        id=receipt_id,
        loom_version_id=version_id,
        filename=file.filename or f"{receipt_id}{ext}",
        path=path,
        description=description,
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    return LoomVersionReceiptSchema.model_validate(receipt)


@router.get("/{loom_id}/versions/{version_id}/receipts/{receipt_id}")
async def get_version_receipt(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    receipt = next((r for r in version.receipts if r.id == receipt_id), None)
    if receipt is None or not storage.file_exists(receipt.path):
        raise HTTPException(status_code=404, detail="Receipt not found")
    data = storage.read_file(receipt.path)
    ct = mimetypes.guess_type(receipt.path)[0] or "application/octet-stream"
    # PDFs open inline in browser; images too
    disposition = "inline" if ct in ("application/pdf", *ALLOWED_IMAGE_TYPES) else "attachment"
    return Response(
        content=data,
        media_type=ct,
        headers={"Content-Disposition": f'{disposition}; filename="{receipt.filename}"'},
    )


@router.delete("/{loom_id}/versions/{version_id}/receipts/{receipt_id}", status_code=204)
async def delete_version_receipt(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    receipt_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    receipt = next((r for r in version.receipts if r.id == receipt_id), None)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    storage.delete_version_receipt(receipt.path)
    await db.delete(receipt)
    await db.commit()


# ---------------------------------------------------------------------------
# Version patch (name / description editable in place)
# ---------------------------------------------------------------------------


@router.patch("/{loom_id}/versions/{version_id}", response_model=LoomVersionSchema)
async def update_version(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    body: UpdateVersionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionSchema:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(version, field, value)
    await db.commit()
    await db.refresh(version, ["photos", "receipts", "accessories"])
    return LoomVersionSchema.model_validate(version)


# ---------------------------------------------------------------------------
# Version clone
# ---------------------------------------------------------------------------


@router.post("/{loom_id}/versions/{version_id}/clone", response_model=LoomVersionSchema, status_code=201)
async def clone_version(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    body: CloneVersionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionSchema:
    loom, source = await _get_owned_version(loom_id, version_id, current_user, db)
    next_number = max((v.version_number for v in loom.versions), default=0) + 1
    new_version = LoomVersion(
        loom_id=loom_id,
        version_number=next_number,
        name=body.name,
        effective_date=body.effective_date,
        description=body.description,
        num_shafts=source.num_shafts,
        num_treadles=source.num_treadles,
        num_heddles=source.num_heddles,
        weaving_width=source.weaving_width,
        weaving_width_unit=source.weaving_width_unit,
        warp_waste_allowance=source.warp_waste_allowance,
        warp_waste_unit=source.warp_waste_unit,
    )
    db.add(new_version)
    await db.flush()

    if body.include_accessories:
        for acc in source.accessories:
            db.add(
                LoomVersionAccessory(
                    loom_version_id=new_version.id,
                    name=acc.name,
                )
            )

    await db.commit()
    await db.refresh(new_version, ["photos", "receipts", "accessories"])
    return LoomVersionSchema.model_validate(new_version)


# ---------------------------------------------------------------------------
# Accessories
# ---------------------------------------------------------------------------


@router.post("/{loom_id}/versions/{version_id}/accessories", response_model=LoomVersionAccessorySchema, status_code=201)
async def add_accessory(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    body: AddAccessoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LoomVersionAccessorySchema:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    acc = LoomVersionAccessory(loom_version_id=version_id, name=body.name.strip())
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return LoomVersionAccessorySchema.model_validate(acc)


@router.delete("/{loom_id}/versions/{version_id}/accessories/{accessory_id}", status_code=204)
async def delete_accessory(
    loom_id: uuid.UUID,
    version_id: uuid.UUID,
    accessory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    loom, version = await _get_owned_version(loom_id, version_id, current_user, db)
    acc = next((a for a in version.accessories if a.id == accessory_id), None)
    if acc is None:
        raise HTTPException(status_code=404, detail="Accessory not found")
    await db.delete(acc)
    await db.commit()
