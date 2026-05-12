import asyncio
import mimetypes
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user, get_db
from app.models.draft import Draft
from app.models.loom import PROJECT_SUPPORTED_LOOM_TYPES, Loom, LoomVersion
from app.models.project import Project, ProjectPhoto, ProjectStep, WeaveSession
from app.models.user import User
from app.services import storage, wif_parser
from app.services.images import resize_to_jpeg
from app.services.storage_quota import check_storage_quota
from app.tasks.preview import generate_drawdown_preview
from app.tasks.tiles import prerender_project_tiles

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_PROJECT_PHOTOS = 10
MAX_PHOTO_SIZE = 25 * 1024 * 1024  # 25 MB raw (resized output is much smaller)
_PROJECT_RESIZE_MAX_PX = 2048


router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProjectPhotoSchema(BaseModel):
    id: uuid.UUID
    filename: str
    display_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    loom_id: uuid.UUID | None
    loom_version_id: uuid.UUID | None
    name: str
    project_type: str
    status: str
    current_pick: int
    total_picks: int
    num_items: int
    length_unit: str
    completed_at: datetime | None
    abandoned_at: datetime | None
    created_at: datetime
    hide_unused_shafts_treadles: bool

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    finished_length_per_item: Decimal | None
    waste_between_items: Decimal | None
    warp_waste_allowance: Decimal | None
    completed_at: datetime | None
    notes: str | None
    draft_name: str
    draft_num_shafts: int | None
    draft_num_treadles: int | None
    draft_effective_num_treadles: int | None
    draft_effective_num_shafts: int | None
    draft_metadata_overrides: dict | None
    loom_name: str | None
    loom_num_treadles: int | None = None
    loom_num_shafts: int | None = None
    photos: list[ProjectPhotoSchema] = []


class CreateProjectRequest(BaseModel):
    name: str
    draft_id: uuid.UUID
    project_type: str  # "treadle" | "lift"
    loom_id: uuid.UUID | None = None
    loom_version_id: uuid.UUID | None = None
    finished_length_per_item: Decimal | None = None
    num_items: int = 1
    waste_between_items: Decimal | None = None
    warp_waste_allowance: Decimal | None = None
    length_unit: str = "cm"


class RenameProjectRequest(BaseModel):
    name: str | None = None
    notes: str | None = None
    hide_unused_shafts_treadles: bool | None = None


class AssignLoomRequest(BaseModel):
    loom_id: uuid.UUID
    loom_version_id: uuid.UUID | None = None


class JumpRequest(BaseModel):
    pick: int


class StepRequest(BaseModel):
    direction: str  # "advance" | "reverse"


class StepResponse(BaseModel):
    current_pick: int
    total_picks: int


class PickRow(BaseModel):
    pick: int
    active: list[int]
    color: str | None = None  # hex weft color e.g. "#ff0000", None if not defined


class PicksResponse(BaseModel):
    project_type: str
    total_picks: int
    picks: list[PickRow]
    has_weft_colors: bool


class SessionInfo(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int


class ProjectMetricsResponse(BaseModel):
    total_sessions: int
    total_session_time_ms: int
    current_session_started_at: datetime | None
    total_advance_steps: int
    total_reverse_steps: int
    total_worked_picks: int
    sessions: list[SessionInfo]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WORKED_PICK_THRESHOLD_MS = 3_000  # < 3 s gap = navigation/review, not a woven pick


async def _close_open_session(project_id: uuid.UUID, db: AsyncSession) -> None:
    open_session = await db.scalar(
        select(WeaveSession).where(WeaveSession.project_id == project_id, WeaveSession.ended_at.is_(None))
    )
    if open_session is not None:
        open_session.ended_at = datetime.now(timezone.utc)


async def _check_loom_conflict(
    loom_id: uuid.UUID, exclude_id: uuid.UUID | None, owner_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raise 409 if the loom already has an active project (other than exclude_id)."""
    q = select(Project).where(
        Project.loom_id == loom_id,
        Project.owner_id == owner_id,
        Project.status == "active",
        Project.deleted_at.is_(None),
    )
    if exclude_id is not None:
        q = q.where(Project.id != exclude_id)
    if await db.scalar(q) is not None:
        raise HTTPException(status_code=409, detail="This loom already has an active project")


async def _wif_path_for_project(draft: Draft, project_type: str) -> str:
    """Return the correct WIF path for a project type.

    For lift projects, prefer the liftplan-augmented file when available so
    that the original upload is never mutated. Falls back to wif_path (covers
    the case where the liftplan was embedded in the original WIF by the user's
    design software).
    """
    if project_type == "lift" and draft.wif_modified_path and await storage.afile_exists(draft.wif_modified_path):
        return draft.wif_modified_path
    return draft.wif_path


async def _get_owned_project(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    with_for_update: bool = False,
) -> Project:
    stmt = select(Project).where(
        Project.id == project_id,
        Project.owner_id == user.id,
        Project.deleted_at.is_(None),
    )
    if with_for_update:
        stmt = stmt.with_for_update()
    project = await db.scalar(stmt)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _resolve_loom_version(project: Project, db: AsyncSession) -> LoomVersion | None:
    """Return the project's loom version, falling back to the loom's only version when loom_version_id is unset."""
    if project.loom_version_id:
        return await db.get(LoomVersion, project.loom_version_id)
    if project.loom_id:
        versions = await db.scalars(select(LoomVersion).where(LoomVersion.loom_id == project.loom_id))
        all_versions = versions.all()
        if len(all_versions) == 1:
            return all_versions[0]
    return None


def _to_detail(
    project: Project,
    draft: Draft,
    loom: Loom | None,
    photos: list[ProjectPhoto] | None = None,
    loom_version: LoomVersion | None = None,
) -> ProjectDetail:
    return ProjectDetail(
        id=project.id,
        draft_id=project.draft_id,
        loom_id=project.loom_id,
        loom_version_id=project.loom_version_id,
        name=project.name,
        project_type=project.project_type,
        status=project.status,
        current_pick=project.current_pick,
        total_picks=project.total_picks,
        finished_length_per_item=project.finished_length_per_item,
        num_items=project.num_items,
        waste_between_items=project.waste_between_items,
        warp_waste_allowance=project.warp_waste_allowance,
        length_unit=project.length_unit,
        completed_at=project.completed_at,
        abandoned_at=project.abandoned_at,
        notes=project.notes,
        created_at=project.created_at,
        hide_unused_shafts_treadles=project.hide_unused_shafts_treadles,
        draft_name=draft.name,
        draft_num_shafts=draft.num_shafts,
        draft_num_treadles=draft.num_treadles,
        draft_effective_num_treadles=draft.effective_num_treadles,
        draft_effective_num_shafts=draft.effective_num_shafts,
        draft_metadata_overrides=draft.metadata_overrides,
        loom_name=f"{loom.manufacturer} {loom.model_name}" if loom else None,
        loom_num_treadles=loom_version.num_treadles if loom_version else None,
        loom_num_shafts=loom_version.num_shafts if loom_version else None,
        photos=[ProjectPhotoSchema.model_validate(p) for p in (photos or [])],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectDetail, status_code=201)
async def create_project(
    body: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.project_type not in ("treadle", "lift"):
        raise HTTPException(status_code=400, detail="project_type must be 'treadle' or 'lift'")

    draft = await db.scalar(
        select(Draft).where(
            Draft.id == body.draft_id,
            Draft.owner_id == current_user.id,
            Draft.deleted_at.is_(None),
        )
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Validate project type is supported by the WIF
    if body.project_type == "treadle" and not draft.has_treadling:
        raise HTTPException(status_code=400, detail="WIF file has no [TREADLING] section")
    if body.project_type == "lift" and not draft.has_liftplan:
        raise HTTPException(status_code=400, detail="WIF file has no [LIFTPLAN] section")

    # Parse pick count from WIF
    wif_bytes = await storage.aread_file(await _wif_path_for_project(draft, body.project_type))
    try:
        pick_data = await asyncio.to_thread(wif_parser.parse_picks, wif_bytes, body.project_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if body.loom_version_id and not body.loom_id:
        raise HTTPException(status_code=400, detail="loom_version_id requires loom_id")

    loom: Loom | None = None
    if body.loom_id:
        loom = await db.scalar(
            select(Loom).where(
                Loom.id == body.loom_id,
                Loom.owner_id == current_user.id,
                Loom.deleted_at.is_(None),
            )
        )
        if loom is None:
            raise HTTPException(status_code=404, detail="Loom not found")

        if loom.loom_type not in PROJECT_SUPPORTED_LOOM_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Loom type '{loom.loom_type}' does not support project tracking",
            )

        if body.loom_version_id:
            version_ok = await db.scalar(
                select(LoomVersion).where(
                    LoomVersion.id == body.loom_version_id,
                    LoomVersion.loom_id == body.loom_id,
                )
            )
            if version_ok is None:
                raise HTTPException(status_code=400, detail="loom_version_id does not belong to the specified loom")

        await _check_loom_conflict(body.loom_id, None, current_user.id, db)

    project = Project(
        owner_id=current_user.id,
        draft_id=body.draft_id,
        loom_id=body.loom_id,
        loom_version_id=body.loom_version_id,
        name=body.name,
        project_type=body.project_type,
        status="active",
        current_pick=1,
        total_picks=pick_data.total_picks,
        finished_length_per_item=body.finished_length_per_item,
        num_items=body.num_items,
        waste_between_items=body.waste_between_items,
        warp_waste_allowance=body.warp_waste_allowance,
        length_unit=body.length_unit,
        hide_unused_shafts_treadles=current_user.hide_unused_shafts_treadles,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    if draft.drawdown_preview_path is None:
        generate_drawdown_preview.delay(str(draft.id))
    from app.config import get_settings
    from app.services.task_history import record_queued

    tile_task = prerender_project_tiles.delay(str(project.id))
    record_queued(get_settings(), tile_task.id, "app.tasks.tiles.prerender_project_tiles", "preview")
    return _to_detail(project, draft, loom)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    draft_id: uuid.UUID | None = Query(None),
    loom_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    q = select(Project).where(Project.owner_id == current_user.id, Project.deleted_at.is_(None))
    if draft_id is not None:
        q = q.where(Project.draft_id == draft_id)
    if loom_id is not None:
        q = q.where(Project.loom_id == loom_id)
    result = await db.scalars(q.order_by(Project.created_at.desc()))
    return [ProjectSummary.model_validate(p) for p in result.all()]


@router.get("/{project_id}/drawdown")
async def get_project_drawdown(
    project_id: uuid.UUID,
    start_row: int | None = Query(None, ge=0),
    row_count: int | None = Query(None, ge=1),
    start_col: int | None = Query(None, ge=0),
    col_count: int | None = Query(None, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from app.config import get_settings
    from app.services import rendering
    from app.services.storage import afile_exists, aproject_tile_exists, aread_file, aread_project_tile

    project = await _get_owned_project(project_id, current_user, db)

    draft = await db.scalar(select(Draft).where(Draft.id == project.draft_id, Draft.deleted_at.is_(None)))
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    wif_path = await _wif_path_for_project(draft, project.project_type)
    if not wif_path or not await afile_exists(wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    _settings = get_settings()
    _sr = start_row or 0
    _rc = row_count
    tile_row_count = _settings.tile_row_count

    warp_count = draft.warp_threads or 0
    weft_count = draft.weft_threads or 0
    if warp_count > 0:
        expected_scale = min(_settings.render_max_width // warp_count, rendering.DRAWDOWN_SCALE)
    else:
        expected_scale = rendering.DRAWDOWN_SCALE

    # Check pre-rendered project tile cache on standard row-boundary alignment.
    # Only for full-width requests (start_col=None) — column-sliced requests must
    # go through render_drawdown_tile so they return the correct pixel slice.
    if (
        start_col is None
        and warp_count > 0
        and _sr % tile_row_count == 0
        and _rc == tile_row_count
        and await aproject_tile_exists(project_id, expected_scale, _sr)
    ):
        cached_png = await aread_project_tile(project_id, expected_scale, _sr)
        actual_rc = min(tile_row_count, weft_count - _sr) if weft_count > 0 else tile_row_count
        return Response(
            content=cached_png,
            media_type="image/png",
            headers={
                "X-Pixels-Per-Row": str(expected_scale),
                "X-Total-Rows": str(weft_count),
                "X-Total-Cols": str(warp_count),
                "X-Start-Row": str(_sr),
                "X-Row-Count": str(actual_rc),
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    wif_bytes = await aread_file(wif_path)
    _sc = start_col
    _cc = col_count
    try:
        result = await asyncio.to_thread(
            lambda: rendering.render_drawdown_tile(
                rendering.load_draft(wif_bytes),
                start_row=_sr,
                row_count=_rc,
                start_col=_sc,
                col_count=_cc,
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drawdown rendering failed: {exc}")

    if len(result) == 7:
        png, total_rows, actual_start, actual_row_count, actual_scale, actual_start_col, actual_col_count = result
    else:
        png, total_rows, actual_start, actual_row_count, actual_scale = result
        actual_start_col = 0
        actual_col_count = warp_count

    # Trigger background tile pre-render on standard boundary miss only when t0 is absent.
    # Only applies to full-width (non-column-sliced) requests.
    if _sc is None and _sr % tile_row_count == 0 and _rc == tile_row_count:
        if not await aproject_tile_exists(project_id, expected_scale, 0):
            from app.services.task_history import record_queued

            tile_task = prerender_project_tiles.apply_async(args=[str(project_id)])
            record_queued(_settings, tile_task.id, "app.tasks.tiles.prerender_project_tiles", "preview")

    extra_headers = (
        {"X-Start-Col": str(actual_start_col), "X-Col-Count": str(actual_col_count)} if _sc is not None else {}
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Pixels-Per-Row": str(actual_scale),
            "X-Total-Rows": str(total_rows),
            "X-Total-Cols": str(warp_count),
            "X-Start-Row": str(actual_start),
            "X-Row-Count": str(actual_row_count),
            "Cache-Control": "no-store",
            **extra_headers,
        },
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    result = await db.scalars(
        select(Project)
        .where(Project.id == project_id, Project.owner_id == current_user.id, Project.deleted_at.is_(None))
        .options(selectinload(Project.photos))
    )
    project = result.first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)
    if draft is not None and draft.drawdown_preview_path is None:
        generate_drawdown_preview.delay(str(draft.id))
    return _to_detail(project, draft, loom, photos=list(project.photos), loom_version=loom_version)  # type: ignore[arg-type]


@router.patch("/{project_id}", response_model=ProjectDetail)
async def rename_project(
    project_id: uuid.UUID,
    body: RenameProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.name is None and body.notes is None and body.hide_unused_shafts_treadles is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")
    project = await _get_owned_project(project_id, current_user, db)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        project.name = name
    if body.notes is not None:
        project.notes = body.notes
    if body.hide_unused_shafts_treadles is not None:
        project.hide_unused_shafts_treadles = body.hide_unused_shafts_treadles
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, draft, loom, loom_version=loom_version)  # type: ignore[arg-type]


@router.post("/{project_id}/assign-loom", response_model=ProjectDetail)
async def assign_loom(
    project_id: uuid.UUID,
    body: AssignLoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status != "active":
        raise HTTPException(status_code=400, detail="Project is not active")
    if project.loom_id is not None:
        raise HTTPException(status_code=400, detail="Project already has a loom assigned")

    loom = await db.scalar(
        select(Loom).where(
            Loom.id == body.loom_id,
            Loom.owner_id == current_user.id,
            Loom.deleted_at.is_(None),
        )
    )
    if loom is None:
        raise HTTPException(status_code=404, detail="Loom not found")

    if loom.loom_type not in PROJECT_SUPPORTED_LOOM_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Loom type '{loom.loom_type}' does not support project tracking",
        )

    if body.loom_version_id:
        version_ok = await db.scalar(
            select(LoomVersion).where(
                LoomVersion.id == body.loom_version_id,
                LoomVersion.loom_id == body.loom_id,
            )
        )
        if version_ok is None:
            raise HTTPException(status_code=400, detail="loom_version_id does not belong to the specified loom")

    await _check_loom_conflict(body.loom_id, None, current_user.id, db)

    project.loom_id = body.loom_id
    project.loom_version_id = body.loom_version_id
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, draft, loom, loom_version=loom_version)


@router.post("/{project_id}/step", response_model=StepResponse)
async def step_project(
    project_id: uuid.UUID,
    body: StepRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StepResponse:
    if body.direction not in ("advance", "reverse"):
        raise HTTPException(status_code=400, detail="direction must be 'advance' or 'reverse'")

    # FOR UPDATE serializes concurrent step requests at the DB level, preventing
    # two simultaneous taps from reading the same current_pick and producing a
    # duplicate increment.
    project = await _get_owned_project(project_id, current_user, db, with_for_update=True)
    if project.status != "active":
        raise HTTPException(status_code=400, detail="Project is not active")

    from_pick = project.current_pick

    if body.direction == "advance":
        if project.current_pick > project.total_picks:
            raise HTTPException(status_code=400, detail="Already at last pick")
        project.current_pick += 1
    else:
        if project.current_pick <= 1:
            raise HTTPException(status_code=400, detail="Already at first pick")
        project.current_pick -= 1

    # Compute dwell and manage session gap-on-arrival
    now = datetime.now(timezone.utc)
    idle_timeout_ms = current_user.idle_timeout_minutes * 60 * 1_000

    last_step = await db.scalar(
        select(ProjectStep).where(ProjectStep.project_id == project_id).order_by(ProjectStep.created_at.desc()).limit(1)
    )

    dwell_ms: int | None = None
    gap_ms: int | None = None
    if last_step is not None:
        last_dt = last_step.created_at
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        gap_ms = int((now - last_dt).total_seconds() * 1_000)
        dwell_ms = min(gap_ms, idle_timeout_ms)

    open_session = await db.scalar(
        select(WeaveSession).where(WeaveSession.project_id == project_id, WeaveSession.ended_at.is_(None))
    )

    is_gap_too_long = gap_ms is not None and gap_ms >= idle_timeout_ms
    if is_gap_too_long and open_session is not None:
        close_dt = last_step.created_at  # type: ignore[union-attr]
        if close_dt.tzinfo is None:
            close_dt = close_dt.replace(tzinfo=timezone.utc)
        open_session.ended_at = close_dt
        open_session = None

    if open_session is None:
        db.add(WeaveSession(project_id=project_id, started_at=now))

    step = ProjectStep(
        project_id=project.id,
        event_type=body.direction,
        from_pick=from_pick,
        to_pick=project.current_pick,
        dwell_ms=dwell_ms,
    )
    db.add(step)
    await db.commit()
    return StepResponse(current_pick=project.current_pick, total_picks=project.total_picks)


@router.post("/{project_id}/jump", response_model=ProjectDetail)
async def jump_project(
    project_id: uuid.UUID,
    body: JumpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status != "active":
        raise HTTPException(status_code=400, detail="Project is not active")
    project.current_pick = max(1, min(body.pick, project.total_picks + 1))
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, draft, loom)  # type: ignore[arg-type]


@router.post("/{project_id}/complete", response_model=ProjectDetail)
async def complete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status != "active":
        raise HTTPException(status_code=400, detail="Project is not active")
    project.status = "completed"
    project.completed_at = datetime.now(timezone.utc)
    await _close_open_session(project_id, db)
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, draft, loom)  # type: ignore[arg-type]


@router.post("/{project_id}/abandon", response_model=ProjectDetail)
async def abandon_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status != "active":
        raise HTTPException(status_code=400, detail="Project is not active")
    project.status = "abandoned"
    project.abandoned_at = datetime.now(timezone.utc)
    await _close_open_session(project_id, db)
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, draft, loom)  # type: ignore[arg-type]


@router.post("/{project_id}/restart", response_model=ProjectDetail)
async def restart_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status != "abandoned":
        raise HTTPException(status_code=400, detail="Only abandoned projects can be restarted")
    if project.loom_id:
        await _check_loom_conflict(project.loom_id, project.id, current_user.id, db)
    project.status = "active"
    await db.commit()
    await db.refresh(project)
    draft = await db.get(Draft, project.draft_id)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    if draft is not None and draft.drawdown_preview_path is None:
        generate_drawdown_preview.delay(str(draft.id))
    return _to_detail(project, draft, loom)  # type: ignore[arg-type]


@router.get("/{project_id}/metrics", response_model=ProjectMetricsResponse)
async def get_project_metrics(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectMetricsResponse:
    await _get_owned_project(project_id, current_user, db)

    now = datetime.now(timezone.utc)

    sessions = (
        await db.scalars(
            select(WeaveSession).where(WeaveSession.project_id == project_id).order_by(WeaveSession.started_at)
        )
    ).all()

    steps = (await db.scalars(select(ProjectStep).where(ProjectStep.project_id == project_id))).all()

    total_advance = sum(1 for s in steps if s.event_type == "advance")
    total_reverse = sum(1 for s in steps if s.event_type == "reverse")
    total_worked = sum(1 for s in steps if s.dwell_ms is not None and s.dwell_ms >= _WORKED_PICK_THRESHOLD_MS)

    total_session_ms = 0
    session_infos: list[SessionInfo] = []
    current_session_started_at: datetime | None = None
    for sess in sessions:
        end = sess.ended_at or now
        duration_ms = int((end - sess.started_at).total_seconds() * 1_000)
        total_session_ms += duration_ms
        session_infos.append(
            SessionInfo(id=sess.id, started_at=sess.started_at, ended_at=sess.ended_at, duration_ms=duration_ms)
        )
        if sess.ended_at is None:
            current_session_started_at = sess.started_at

    return ProjectMetricsResponse(
        total_sessions=len(sessions),
        total_session_time_ms=total_session_ms,
        current_session_started_at=current_session_started_at,
        total_advance_steps=total_advance,
        total_reverse_steps=total_reverse,
        total_worked_picks=total_worked,
        sessions=session_infos,
    )


@router.post("/{project_id}/clone", response_model=ProjectDetail, status_code=201)
async def clone_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    source = await _get_owned_project(project_id, current_user, db)
    if source.loom_id:
        await _check_loom_conflict(source.loom_id, None, current_user.id, db)
    clone = Project(
        owner_id=current_user.id,
        draft_id=source.draft_id,
        loom_id=source.loom_id,
        loom_version_id=source.loom_version_id,
        name=source.name,
        project_type=source.project_type,
        status="active",
        current_pick=1,
        total_picks=source.total_picks,
        finished_length_per_item=source.finished_length_per_item,
        num_items=source.num_items,
        waste_between_items=source.waste_between_items,
        warp_waste_allowance=source.warp_waste_allowance,
        length_unit=source.length_unit,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    draft = await db.get(Draft, clone.draft_id)
    loom = await db.get(Loom, clone.loom_id) if clone.loom_id else None
    if draft is not None and draft.drawdown_preview_path is None:
        generate_drawdown_preview.delay(str(draft.id))
    return _to_detail(clone, draft, loom)  # type: ignore[arg-type]


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await _get_owned_project(project_id, current_user, db)
    project.soft_delete()
    await db.commit()


@router.post("/{project_id}/photos", response_model=ProjectPhotoSchema, status_code=201)
async def upload_project_photo(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectPhotoSchema:
    project = await _get_owned_project(project_id, current_user, db)

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WebP, and HEIC images are allowed")

    data = await file.read()
    if len(data) > MAX_PHOTO_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large (max {MAX_PHOTO_SIZE // (1024 * 1024)} MB)")

    existing = await db.scalars(select(ProjectPhoto).where(ProjectPhoto.project_id == project.id))
    if len(existing.all()) >= MAX_PROJECT_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PROJECT_PHOTOS} photos per project")

    try:
        data = resize_to_jpeg(data, max_px=_PROJECT_RESIZE_MAX_PX)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process image file")

    await check_storage_quota(current_user.id, db, incoming_bytes=len(data))

    photo_id = uuid.uuid4()
    file_path = await storage.asave_project_photo(project.id, photo_id, ".jpg", data)

    max_order_result = await db.scalars(
        select(ProjectPhoto.display_order)
        .where(ProjectPhoto.project_id == project.id)
        .order_by(ProjectPhoto.display_order.desc())
        .limit(1)
    )
    max_order: int = max_order_result.first() or 0

    photo = ProjectPhoto(
        id=photo_id,
        project_id=project.id,
        file_path=file_path,
        filename=file.filename or "photo.jpg",
        file_size_bytes=len(data),
        display_order=max_order + 1,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return ProjectPhotoSchema.model_validate(photo)


@router.get("/{project_id}/photos/{photo_id}")
async def get_project_photo(
    project_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_owned_project(project_id, current_user, db)
    photo = await db.scalar(
        select(ProjectPhoto).where(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project_id)
    )
    if photo is None or not await storage.afile_exists(photo.file_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    data = await storage.aread_file(photo.file_path)
    ct = mimetypes.guess_type(photo.file_path)[0] or "application/octet-stream"
    return Response(content=data, media_type=ct)


@router.delete("/{project_id}/photos/{photo_id}", status_code=204)
async def delete_project_photo(
    project_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_owned_project(project_id, current_user, db)
    photo = await db.scalar(
        select(ProjectPhoto).where(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project_id)
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await storage.adelete_project_photo(photo.file_path)
    await db.delete(photo)
    await db.commit()


@router.get("/{project_id}/picks", response_model=PicksResponse)
async def get_picks(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PicksResponse:
    project = await _get_owned_project(project_id, current_user, db)
    draft = await db.get(Draft, project.draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    wif_bytes = await storage.aread_file(await _wif_path_for_project(draft, project.project_type))
    try:
        pick_data = await asyncio.to_thread(wif_parser.parse_picks, wif_bytes, project.project_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pick_rows = [
        PickRow(pick=i + 1, active=row, color=pick_data.weft_colors[i]) for i, row in enumerate(pick_data.picks)
    ]
    return PicksResponse(
        project_type=pick_data.project_type,
        total_picks=pick_data.total_picks,
        picks=pick_rows,
        has_weft_colors=any(p.color is not None for p in pick_rows),
    )
