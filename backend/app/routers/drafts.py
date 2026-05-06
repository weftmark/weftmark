import urllib.parse
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db
from app.models.draft import Draft
from app.models.user import User
from app.services import rendering, storage, wif_linter, wif_modifier, wif_parser
from app.services.rate_limiter import rate_limit

router = APIRouter(prefix="/api/drafts", tags=["drafts"])
settings = get_settings()

_upload_rate_limit = rate_limit("wif_upload", max_requests=30, window_seconds=3600)

_WIF_MAGIC = b"[WIF]"


def _content_disposition(filename: str) -> str:
    ascii_fallback = "".join(c if c.isascii() and c not in '"\\\r\n' else "_" for c in filename)
    encoded = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DraftSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    wif_filename: str
    num_shafts: int | None
    num_treadles: int | None
    effective_num_treadles: int | None
    effective_num_shafts: int | None
    warp_threads: int | None
    weft_threads: int | None
    has_threading: bool
    has_tieup: bool
    has_treadling: bool
    has_liftplan: bool
    liftplan_generated: bool
    has_color_palette: bool
    lint_warnings: list[str]
    lint_errors: list[str]
    has_preview: bool
    has_modified_file: bool
    metadata_overrides: dict | None
    is_shared: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_draft(cls, d: Draft) -> "DraftSummary":
        data = {c.key: getattr(d, c.key) for c in d.__table__.columns}
        data["has_preview"] = storage.preview_exists(d.preview_path)
        data["has_modified_file"] = bool(d.wif_modified_path and storage.file_exists(d.wif_modified_path))
        return cls(**data)


class DraftDetail(DraftSummary):
    wif_source_software: str | None
    wif_source_version: str | None


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("", response_model=DraftSummary, status_code=201)
async def create_draft(
    name: Annotated[str, Form()],
    wif_file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(_upload_rate_limit),
) -> DraftSummary:
    if not wif_file.filename or not wif_file.filename.lower().endswith(".wif"):
        raise HTTPException(status_code=400, detail="File must have a .wif extension")

    wif_bytes = await wif_file.read()
    if len(wif_bytes) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")
    if not wif_bytes.lstrip()[:5].upper() == _WIF_MAGIC:
        raise HTTPException(status_code=400, detail="File does not appear to be a valid WIF file")

    lint = wif_linter.lint(wif_bytes)

    draft = Draft(
        owner_id=current_user.id,
        name=name,
        description=description,
        wif_filename=wif_file.filename,
        wif_path="",  # set after we have the draft id
        num_shafts=lint.num_shafts,
        num_treadles=lint.num_treadles,
        effective_num_treadles=lint.effective_num_treadles,
        effective_num_shafts=lint.effective_num_shafts,
        warp_threads=lint.warp_threads,
        weft_threads=lint.weft_threads,
        has_threading=lint.has_threading,
        has_tieup=lint.has_tieup,
        has_treadling=lint.has_treadling,
        has_liftplan=lint.has_liftplan,
        has_color_palette=lint.has_color_palette,
        lint_warnings=lint.warnings,
        lint_errors=lint.errors,
        wif_source_software=lint.source_software,
        wif_source_version=lint.source_version,
    )
    db.add(draft)
    await db.flush()  # get draft.id without committing

    draft.wif_path = storage.save_wif(draft.id, wif_file.filename, wif_bytes)

    # Render preview if parseable
    if lint.is_parseable and not lint.errors:
        try:
            wif_draft = rendering.load_draft(wif_bytes)
            png = rendering.render_full_draft(wif_draft)
            draft.preview_path = storage.save_preview(draft.id, png)
        except Exception as exc:
            draft.lint_warnings = list(draft.lint_warnings) + [f"Preview rendering failed: {exc}"]

    await db.commit()
    await db.refresh(draft)
    return DraftSummary.from_draft(draft)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=list[DraftSummary])
async def list_drafts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DraftSummary]:
    result = await db.scalars(
        select(Draft)
        .where(Draft.owner_id == current_user.id, Draft.deleted_at.is_(None))
        .order_by(Draft.created_at.desc())
    )
    return [DraftSummary.from_draft(d) for d in result.all()]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{draft_id}", response_model=DraftDetail)
async def get_draft(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftDetail:
    draft = await _get_owned_draft(draft_id, current_user, db)
    return DraftDetail(**_draft_detail_data(draft))


# ---------------------------------------------------------------------------
# Preview image
# ---------------------------------------------------------------------------


@router.get("/{draft_id}/preview")
async def get_preview(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    draft = await _get_owned_draft(draft_id, current_user, db)
    if not storage.preview_exists(draft.preview_path):
        raise HTTPException(status_code=404, detail="Preview not available")
    png = storage.read_preview(draft.preview_path)  # type: ignore[arg-type]
    return Response(content=png, media_type="image/png")


# ---------------------------------------------------------------------------
# Drawdown-only image
# ---------------------------------------------------------------------------


@router.get("/{draft_id}/drawdown")
async def get_drawdown(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    draft = await _get_owned_draft(draft_id, current_user, db)
    if not draft.wif_path:
        raise HTTPException(status_code=404, detail="No WIF file for this draft")

    if not storage.file_exists(draft.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    wif_bytes = storage.read_file(draft.wif_path)
    try:
        wif_draft = rendering.load_draft(wif_bytes)
        png, total_rows = rendering.render_drawdown_only(wif_draft)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drawdown rendering failed: {exc}")

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Pixels-Per-Row": str(rendering.DRAWDOWN_SCALE),
            "X-Total-Rows": str(total_rows),
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{draft_id}"',
        },
    )


# ---------------------------------------------------------------------------
# WIF download
# ---------------------------------------------------------------------------


@router.get("/{draft_id}/wif")
async def download_wif(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    draft = await _get_owned_draft(draft_id, current_user, db)
    if not draft.wif_path or not storage.file_exists(draft.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not available for this draft")
    wif_bytes = storage.read_file(draft.wif_path)
    filename = draft.wif_filename or "draft.wif"
    return Response(
        content=wif_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# ---------------------------------------------------------------------------
# WIF with generated lift plan download
# ---------------------------------------------------------------------------


@router.get("/{draft_id}/wif-modified")
async def download_wif_modified(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    draft = await _get_owned_draft(draft_id, current_user, db)
    if not draft.wif_modified_path or not storage.file_exists(draft.wif_modified_path):
        raise HTTPException(status_code=404, detail="No modified WIF file for this draft")
    wif_bytes = storage.read_file(draft.wif_modified_path)
    base = (draft.wif_filename or "draft.wif").rsplit(".", 1)[0]
    filename = f"{base}-modified.wif"
    return Response(
        content=wif_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


@router.delete("/{draft_id}", status_code=204)
async def delete_draft(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    draft = await _get_owned_draft(draft_id, current_user, db)
    draft.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Generate lift plan
# ---------------------------------------------------------------------------


@router.post("/{draft_id}/generate-liftplan", response_model=DraftDetail)
async def generate_liftplan(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftDetail:
    draft = await _get_owned_draft(draft_id, current_user, db)

    if not draft.has_treadling:
        raise HTTPException(status_code=400, detail="WIF file has no [TREADLING] section — cannot compute lift plan")
    if not draft.has_tieup:
        raise HTTPException(status_code=400, detail="WIF file has no [TIEUP] section — cannot compute lift plan")

    # Read from modified file if one exists (to chain onto prior modifications)
    has_mod = draft.wif_modified_path and storage.file_exists(draft.wif_modified_path)
    source_path = draft.wif_modified_path if has_mod else draft.wif_path
    wif_bytes = storage.read_file(source_path)
    try:
        updated_bytes = wif_parser.compute_liftplan(wif_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    modified_filename = draft.wif_filename.rsplit(".", 1)[0] + "-modified.wif"
    draft.wif_modified_path = storage.save_wif(draft.id, modified_filename, updated_bytes)
    draft.has_liftplan = True
    draft.liftplan_generated = True

    await db.commit()
    await db.refresh(draft)
    return DraftDetail(**_draft_detail_data(draft))


# ---------------------------------------------------------------------------
# Override WIF metadata
# ---------------------------------------------------------------------------

_OVERRIDE_FIELDS = {
    "num_treadles": "Treadles",
    "num_shafts": "Shafts",
}


class OverrideMetadataRequest(BaseModel):
    field: str  # "num_treadles" | "num_shafts"
    value: int


@router.post("/{draft_id}/override-metadata", response_model=DraftDetail)
async def override_metadata(
    draft_id: uuid.UUID,
    body: OverrideMetadataRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DraftDetail:
    if body.field not in _OVERRIDE_FIELDS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported field '{body.field}'. Allowed: {list(_OVERRIDE_FIELDS)}"
        )
    if body.value < 1:
        raise HTTPException(status_code=400, detail="Value must be >= 1")

    draft = await _get_owned_draft(draft_id, current_user, db)

    # Read from modified file if one already exists, otherwise original
    source_path = (
        draft.wif_modified_path
        if draft.wif_modified_path and storage.file_exists(draft.wif_modified_path)
        else draft.wif_path
    )
    wif_bytes = storage.read_file(source_path)

    wif_key = _OVERRIDE_FIELDS[body.field]
    try:
        updated_bytes = wif_modifier.set_weaving_int(wif_bytes, wif_key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    modified_filename = draft.wif_filename.rsplit(".", 1)[0] + "-modified.wif"
    draft.wif_modified_path = storage.save_wif(draft.id, modified_filename, updated_bytes)

    # Record the override (original value preserved for display)
    original_value = getattr(draft, body.field)
    overrides = dict(draft.metadata_overrides or {})
    overrides[body.field] = {"original": original_value, "override": body.value}
    draft.metadata_overrides = overrides

    # Update the live metadata value on the draft
    setattr(draft, body.field, body.value)

    # Re-lint the updated WIF so the mismatch warning is cleared
    lint = wif_linter.lint(updated_bytes)
    draft.lint_warnings = lint.warnings
    draft.lint_errors = lint.errors

    await db.commit()
    await db.refresh(draft)
    return DraftDetail(**_draft_detail_data(draft))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draft_detail_data(draft: Draft) -> dict:
    """Build the data dict for DraftDetail, filtering any mismatch lint warnings
    that are already covered by a metadata override so stale DB entries don't show."""
    data = {c.key: getattr(draft, c.key) for c in draft.__table__.columns}
    data["has_preview"] = storage.preview_exists(draft.preview_path)
    data["has_modified_file"] = bool(draft.wif_modified_path and storage.file_exists(draft.wif_modified_path))
    overrides = draft.metadata_overrides or {}
    warnings = list(data.get("lint_warnings") or [])
    if "num_treadles" in overrides:
        warnings = [w for w in warnings if "[WEAVING] declares Treadles=" not in w]
    if "num_shafts" in overrides:
        warnings = [w for w in warnings if "[WEAVING] declares Shafts=" not in w]
    data["lint_warnings"] = warnings
    return data


async def _get_owned_draft(draft_id: uuid.UUID, user: User, db: AsyncSession) -> Draft:
    draft = await db.scalar(
        select(Draft).where(
            Draft.id == draft_id,
            Draft.owner_id == user.id,
            Draft.deleted_at.is_(None),
        )
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft
