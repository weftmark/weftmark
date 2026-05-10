import asyncio
import urllib.parse
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db
from app.models.draft import Draft
from app.models.user import User
from app.services import rendering, storage, wif_linter, wif_modifier, wif_parser
from app.services.audit import write_audit_log
from app.services.rate_limiter import rate_limit
from app.tasks.preview import generate_drawdown_preview
from app.tasks.tiles import prerender_drawdown_tiles

router = APIRouter(prefix="/api/drafts", tags=["drafts"])
settings = get_settings()

_upload_rate_limit = rate_limit("wif_upload", max_requests=30, window_seconds=3600)


def _has_wif_header(data: bytes) -> bool:
    """Return True if data contains a [WIF] section header within the first 20 lines.

    Skips leading INI comment lines (starting with ';') per the WIF spec.
    Stops at the first non-comment, non-empty line if it isn't [WIF].
    """
    for line in data.splitlines()[:20]:
        stripped = line.strip()
        if stripped.upper() == b"[WIF]":
            return True
        if stripped and not stripped.startswith(b";"):
            return False
    return False


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
    has_drawdown_preview: bool
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
        data["has_drawdown_preview"] = storage.drawdown_preview_exists(d.drawdown_preview_path)
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
    if not _has_wif_header(wif_bytes):
        first_line = wif_bytes.splitlines()[0].decode(errors="replace")[:60] if wif_bytes else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"File does not appear to be a valid WIF file. "
                f"Expected a [WIF] section header (comment lines starting with ';' are allowed). "
                f"First line of uploaded file: {first_line!r}"
            ),
        )

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

    draft.wif_path = await storage.asave_wif(draft.id, wif_file.filename, wif_bytes)

    await db.commit()
    await db.refresh(draft)
    if draft.wif_path:
        from app.config import get_settings
        from app.services.task_history import record_queued

        task = generate_drawdown_preview.delay(str(draft.id))
        record_queued(get_settings(), task.id, "app.tasks.preview.generate_drawdown_preview", "preview")
        tile_task = prerender_drawdown_tiles.delay(str(draft.id))
        record_queued(get_settings(), tile_task.id, "app.tasks.tiles.prerender_drawdown_tiles", "preview")
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
    if not await storage.afile_exists(draft.preview_path):
        raise HTTPException(status_code=404, detail="Preview not available")
    png = await storage.aread_file(draft.preview_path)  # type: ignore[arg-type]
    return Response(content=png, media_type="image/png")


# ---------------------------------------------------------------------------
# Drawdown-only image
# ---------------------------------------------------------------------------


@router.get("/{draft_id}/drawdown")
async def get_drawdown(
    draft_id: uuid.UUID,
    start_row: int | None = Query(None, ge=0),
    row_count: int | None = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    draft = await _get_owned_draft(draft_id, current_user, db)

    # Tiled request: check pre-rendered tile cache first, then render on-demand
    if start_row is not None or row_count is not None:
        if not draft.wif_path:
            raise HTTPException(status_code=404, detail="No WIF file for this draft")
        if not await storage.afile_exists(draft.wif_path):
            raise HTTPException(status_code=404, detail="WIF file not found in storage")

        _sr = start_row or 0
        _rc = row_count

        # Check pre-rendered tile cache when request aligns with standard boundaries
        tile_row_count = settings.tile_row_count
        warp_count = draft.warp_threads or 0
        weft_count = draft.weft_threads or 0
        if warp_count > 0:
            expected_scale = min(settings.render_max_width // warp_count, rendering.DRAWDOWN_SCALE)
        else:
            expected_scale = rendering.DRAWDOWN_SCALE

        if (
            warp_count > 0
            and _sr % tile_row_count == 0
            and _rc == tile_row_count
            and await storage.adrawdown_tile_exists(draft_id, expected_scale, _sr)
        ):
            cached_png = await storage.aread_drawdown_tile(draft_id, expected_scale, _sr)
            actual_rc = min(tile_row_count, weft_count - _sr) if weft_count > 0 else tile_row_count
            return Response(
                content=cached_png,
                media_type="image/png",
                headers={
                    "X-Pixels-Per-Row": str(expected_scale),
                    "X-Total-Rows": str(weft_count),
                    "X-Start-Row": str(_sr),
                    "X-Row-Count": str(actual_rc),
                    "Cache-Control": "public, max-age=31536000, immutable",
                },
            )

        wif_bytes = await storage.aread_file(draft.wif_path)
        try:
            png, total_rows, actual_start, actual_row_count, actual_scale = await asyncio.to_thread(
                lambda: rendering.render_drawdown_tile(rendering.load_draft(wif_bytes), start_row=_sr, row_count=_rc)
            )
        except HTTPException as exc:
            if exc.status_code == 413:
                await write_audit_log(
                    db,
                    event_type="render.limit_exceeded",
                    actor=current_user,
                    details={
                        "draft_id": str(draft_id),
                        "warp_threads": draft.warp_threads,
                        "weft_threads": draft.weft_threads,
                        "render_max_width": settings.render_max_width,
                        "render_max_height": settings.render_max_height,
                        "mode": "tile",
                    },
                )
                await db.commit()
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Drawdown rendering failed: {exc}")

        # Trigger background tile pre-render on standard cache miss, but only if
        # t0 doesn't exist yet — avoids double-fire when eager prerender already ran.
        if _sr % tile_row_count == 0 and _rc == tile_row_count:
            if not await storage.adrawdown_tile_exists(draft_id, expected_scale, 0):
                from app.services.task_history import record_queued

                tile_task = prerender_drawdown_tiles.apply_async(args=[str(draft_id)])
                record_queued(settings, tile_task.id, "app.tasks.tiles.prerender_drawdown_tiles", "preview")

        return Response(
            content=png,
            media_type="image/png",
            headers={
                "X-Pixels-Per-Row": str(actual_scale),
                "X-Total-Rows": str(total_rows),
                "X-Start-Row": str(actual_start),
                "X-Row-Count": str(actual_row_count),
                "Cache-Control": "no-store",
            },
        )

    # Non-tiled: serve pre-generated cached preview if available
    if draft.drawdown_preview_path and await storage.afile_exists(draft.drawdown_preview_path):
        png = await storage.aread_drawdown_preview(draft.drawdown_preview_path)
        scale = draft.drawdown_preview_scale or rendering.DRAWDOWN_SCALE
        total_rows = draft.weft_threads or 0
        return Response(
            content=png,
            media_type="image/png",
            headers={
                "X-Pixels-Per-Row": str(scale),
                "X-Total-Rows": str(total_rows),
                "Cache-Control": "public, max-age=31536000, immutable",
                "ETag": f'"{draft_id}"',
            },
        )

    # Fall back to live render
    if not draft.wif_path:
        raise HTTPException(status_code=404, detail="No WIF file for this draft")

    if not await storage.afile_exists(draft.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    wif_bytes = await storage.aread_file(draft.wif_path)
    try:
        png, total_rows, actual_scale = await asyncio.to_thread(
            lambda: rendering.render_drawdown_only(rendering.load_draft(wif_bytes))
        )
    except HTTPException as exc:
        if exc.status_code == 413:
            await write_audit_log(
                db,
                event_type="render.limit_exceeded",
                actor=current_user,
                details={
                    "draft_id": str(draft_id),
                    "warp_threads": draft.warp_threads,
                    "weft_threads": draft.weft_threads,
                    "render_max_width": settings.render_max_width,
                    "render_max_height": settings.render_max_height,
                    "mode": "full",
                },
            )
            await db.commit()
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drawdown rendering failed: {exc}")

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Pixels-Per-Row": str(actual_scale),
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
    if not draft.wif_path or not await storage.afile_exists(draft.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not available for this draft")
    wif_bytes = await storage.aread_file(draft.wif_path)
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
    if not draft.wif_modified_path or not await storage.afile_exists(draft.wif_modified_path):
        raise HTTPException(status_code=404, detail="No modified WIF file for this draft")
    wif_bytes = await storage.aread_file(draft.wif_modified_path)
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
    has_mod = draft.wif_modified_path and await storage.afile_exists(draft.wif_modified_path)
    source_path = draft.wif_modified_path if has_mod else draft.wif_path
    wif_bytes = await storage.aread_file(source_path)
    try:
        updated_bytes = await asyncio.to_thread(wif_parser.compute_liftplan, wif_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    modified_filename = draft.wif_filename.rsplit(".", 1)[0] + "-modified.wif"
    draft.wif_modified_path = await storage.asave_wif(draft.id, modified_filename, updated_bytes)
    draft.has_liftplan = True
    draft.liftplan_generated = True

    await db.commit()
    await db.refresh(draft)
    _prev_task = generate_drawdown_preview.delay(str(draft.id))
    from app.config import get_settings
    from app.services.task_history import record_queued

    record_queued(get_settings(), _prev_task.id, "app.tasks.preview.generate_drawdown_preview", "preview")
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
    _prev_task2 = generate_drawdown_preview.delay(str(draft.id))
    from app.config import get_settings
    from app.services.task_history import record_queued

    record_queued(get_settings(), _prev_task2.id, "app.tasks.preview.generate_drawdown_preview", "preview")
    return DraftDetail(**_draft_detail_data(draft))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draft_detail_data(draft: Draft) -> dict:
    """Build the data dict for DraftDetail, filtering any mismatch lint warnings
    that are already covered by a metadata override so stale DB entries don't show."""
    data = {c.key: getattr(draft, c.key) for c in draft.__table__.columns}
    data["has_preview"] = storage.preview_exists(draft.preview_path)
    data["has_drawdown_preview"] = storage.drawdown_preview_exists(draft.drawdown_preview_path)
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
