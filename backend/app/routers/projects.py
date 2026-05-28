import asyncio
import mimetypes
import re
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user, get_db
from app.models.draft import Draft
from app.models.loom import PROJECT_SUPPORTED_LOOM_TYPES, Loom, LoomVersion, loom_tracking_flags
from app.models.project import Project, ProjectDraft, ProjectPhoto, ProjectStep, ProjectYarnColor, WeaveSession
from app.models.user import User
from app.models.yarn import Yarn
from app.services import storage, wif_parser
from app.services.images import resize_to_jpeg, validate_image_format
from app.services.storage_quota import check_storage_quota
from app.tasks.preview import (
    generate_drawdown_preview,
    generate_project_drawdown_preview,
    generate_project_drawdown_svg,
)
from app.tasks.tiles import prerender_project_tiles

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}  # fast pre-filter only
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


class ProjectYarnColorSchema(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    yarn_id: uuid.UUID | None
    color_hex: str
    use_yarn_photo: bool
    yarn_brand: str | None = None
    yarn_name: str | None = None
    yarn_color_name: str | None = None
    yarn_color_hex: str | None = None
    yarn_has_photo: bool = False

    model_config = {"from_attributes": True}


class ProjectDraftSchema(BaseModel):
    id: uuid.UUID
    draft_id: uuid.UUID
    position: int
    repeats: int
    current_pick: int
    draft_name: str
    draft_total_picks: int  # draft.weft_threads (picks per single pass)
    section_total_picks: int  # draft_total_picks * repeats
    is_active: bool  # matches project.current_position
    has_treadling: bool
    has_liftplan: bool

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    loom_id: uuid.UUID | None
    loom_version_id: uuid.UUID | None
    name: str
    project_type: str | None  # null until loom assigned
    status: str
    current_position: int
    # Active position conveniences (mirrors tracker expectations)
    current_pick: int  # active sequence entry's current_pick
    current_item: int
    num_items: int
    length_unit: str
    # Aggregate progress across the full sequence
    total_picks: int  # sum of section_total_picks
    aggregate_current_pick: int  # sum of current_pick across all positions
    # List-view draft info
    draft_id: uuid.UUID | None  # primary (position-1) draft id, for thumbnail lookup
    draft_count: int
    draft_sequence: list[ProjectDraftSchema] = []
    completed_at: datetime | None
    abandoned_at: datetime | None
    created_at: datetime
    hide_unused_shafts_treadles: bool
    has_drawdown_preview: bool = False
    has_drawdown_svg: bool = False
    share_slug: str | None = None
    share_visibility: str = "private"
    share_expires_at: datetime | None = None
    tags: list[str] = []

    model_config = {"from_attributes": True}


class ProjectDetail(BaseModel):
    # All Summary fields
    id: uuid.UUID
    owner_id: uuid.UUID
    loom_id: uuid.UUID | None
    loom_version_id: uuid.UUID | None
    name: str
    project_type: str | None
    status: str
    current_position: int
    current_pick: int
    current_item: int
    num_items: int
    length_unit: str
    total_picks: int
    aggregate_current_pick: int
    draft_id: uuid.UUID | None
    draft_count: int
    draft_sequence: list[ProjectDraftSchema] = []
    completed_at: datetime | None
    abandoned_at: datetime | None
    created_at: datetime
    hide_unused_shafts_treadles: bool
    has_drawdown_preview: bool = False
    has_drawdown_svg: bool = False
    share_slug: str | None = None
    share_visibility: str = "private"
    share_expires_at: datetime | None = None
    tags: list[str] = []
    # Detail-only fields (from active draft)
    finished_length_per_item: Decimal | None
    waste_between_items: Decimal | None
    warp_waste_allowance: Decimal | None
    notes: str | None
    draft_name: str | None = None
    draft_num_shafts: int | None = None
    draft_num_treadles: int | None = None
    draft_effective_num_treadles: int | None = None
    draft_effective_num_shafts: int | None = None
    draft_metadata_overrides: dict | None = None
    draft_wif_colors: list | None = None
    draft_warp_color_stats: list | None = None
    draft_weft_color_stats: list | None = None
    draft_wif_measurements: dict | None = None
    draft_warp_threads: int | None = None
    draft_weft_threads: int | None = None
    draft_warp_length_cm: float | None = None
    draft_weaving_width_override_cm: float | None = None
    draft_epi_override: float | None = None
    color_replacements: dict | None = None
    loom_name: str | None = None
    loom_num_treadles: int | None = None
    loom_num_shafts: int | None = None
    loom_warp_waste_allowance: Decimal | None = None
    loom_warp_waste_unit: str | None = None
    loom_resolved_version_id: uuid.UUID | None = None
    loom_reeds: list[dict] = []
    reed_dents_per_inch: float | None = None
    photos: list[ProjectPhotoSchema] = []
    yarn_colors: list[ProjectYarnColorSchema] = []

    model_config = {"from_attributes": True}


class CreateProjectRequest(BaseModel):
    name: str
    loom_id: uuid.UUID | None = None
    loom_version_id: uuid.UUID | None = None
    finished_length_per_item: Decimal | None = None
    num_items: int = 1
    waste_between_items: Decimal | None = None
    warp_waste_allowance: Decimal | None = None
    length_unit: str = "cm"
    tags: list[str] = []


class RenameProjectRequest(BaseModel):
    name: str | None = None
    notes: str | None = None
    hide_unused_shafts_treadles: bool | None = None
    tags: list[str] | None = None


class WarpSetupRequest(BaseModel):
    num_items: int | None = None
    finished_length_per_item: Decimal | None = None
    waste_between_items: Decimal | None = None
    warp_waste_allowance: Decimal | None = None
    length_unit: str | None = None


class ColorReplacementsRequest(BaseModel):
    color_replacements: dict[str, str]


class AssignLoomRequest(BaseModel):
    loom_id: uuid.UUID
    loom_version_id: uuid.UUID | None = None


class SetReedRequest(BaseModel):
    reed_dents_per_inch: float | None


class JumpRequest(BaseModel):
    pick: int


class JumpItemRequest(BaseModel):
    item: int


class StepRequest(BaseModel):
    direction: str  # "advance" | "reverse"


class StepResponse(BaseModel):
    current_pick: int  # active position's current_pick
    total_picks: int  # active position's section_total_picks
    position: int  # which sequence position is active
    aggregate_current_pick: int
    aggregate_total_picks: int
    current_item: int
    num_items: int


class AddSequenceEntryRequest(BaseModel):
    draft_id: uuid.UUID
    repeats: int = 1


class UpdateSequenceEntryRequest(BaseModel):
    repeats: int | None = None


class ReorderSequenceRequest(BaseModel):
    ordered_ids: list[uuid.UUID]  # project_drafts.id in desired order


class PickRow(BaseModel):
    pick: int
    active: list[int]
    color: str | None = None  # hex weft color e.g. "#ff0000", None if not defined


class PicksResponse(BaseModel):
    project_type: str
    total_picks: int
    picks: list[PickRow]
    has_weft_colors: bool


class WarpingPlanEndEntry(BaseModel):
    end: int
    shafts: list[int]
    color: str | None


class WarpingPlanColorRun(BaseModel):
    color: str | None
    color_name: str | None = None
    start_end: int
    end_end: int
    count: int


class WarpingPlanResponse(BaseModel):
    project_id: uuid.UUID
    draft_name: str
    project_type: str | None
    warp_threads: int | None
    total_picks: int | None
    num_shafts: int | None
    num_treadles: int | None
    warp_color_summary: list[dict]
    weft_color_summary: list[dict]
    threading: list[WarpingPlanEndEntry] | None
    warp_color_runs: list[WarpingPlanColorRun] | None
    warp_length_cm: float | None
    epi: float | None
    has_threading: bool
    tieup: list[list[int]] | None = None
    tieup_num_shafts: int | None = None
    tieup_num_treadles: int | None = None
    has_tieup: bool = False


class SessionInfo(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int
    step_count: int


class ProjectMetricsResponse(BaseModel):
    total_sessions: int
    total_session_time_ms: int
    current_session_started_at: datetime | None
    total_advance_steps: int
    total_reverse_steps: int
    total_worked_picks: int
    avg_pick_dwell_ms: int | None
    sessions: list[SessionInfo]


class ShareProjectRequest(BaseModel):
    visibility: str  # "link"
    expires_at: datetime | None = None


class SharedProjectResponse(BaseModel):
    slug: str
    project_name: str
    project_status: str
    project_type: str | None
    owner_display_name: str
    draft_name: str | None
    draft_num_shafts: int | None
    draft_num_treadles: int | None
    num_items: int
    total_picks: int
    current_pick: int
    current_item: int
    share_visibility: str
    share_expires_at: datetime | None
    created_at: datetime
    completed_at: datetime | None
    abandoned_at: datetime | None
    has_drawdown_preview: bool
    has_drawdown_svg: bool
    color_replacements: dict | None
    draft_wif_colors: list | None
    draft_warp_color_stats: list | None
    draft_weft_color_stats: list | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WORKED_PICK_THRESHOLD_MS = 3_000  # < 3 s gap = navigation/review, not a woven pick

share_router = APIRouter(prefix="/api/share", tags=["share"])

_SLUG_MAX_NAME_CHARS = 48
_SLUG_SUFFIX_BYTES = 3  # → 4 base64url chars


def _slugify(name: str) -> str:
    """Convert a project name to a URL-safe slug segment."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:_SLUG_MAX_NAME_CHARS].rstrip("-") or "project"


async def _generate_unique_slug(name: str, db: AsyncSession, max_attempts: int = 8) -> str:
    base = _slugify(name)
    for _ in range(max_attempts):
        suffix = secrets.token_urlsafe(_SLUG_SUFFIX_BYTES)
        candidate = f"{base}-{suffix}"
        existing = await db.scalar(select(Project).where(Project.share_slug == candidate))
        if existing is None:
            return candidate
    raise HTTPException(status_code=500, detail="Could not generate unique share slug")


async def _close_open_session(project_id: uuid.UUID, db: AsyncSession) -> None:
    open_session = await db.scalar(
        select(WeaveSession).where(WeaveSession.project_id == project_id, WeaveSession.ended_at.is_(None))
    )
    if open_session is not None:
        open_session.ended_at = datetime.now(timezone.utc)


async def _check_loom_conflict(
    loom_id: uuid.UUID, exclude_id: uuid.UUID | None, owner_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raise 409 if the loom already has an active or not-yet-started project (other than exclude_id)."""
    q = select(Project).where(
        Project.loom_id == loom_id,
        Project.owner_id == owner_id,
        Project.status.in_(("created", "active")),
        Project.deleted_at.is_(None),
    )
    if exclude_id is not None:
        q = q.where(Project.id != exclude_id)
    if await db.scalar(q) is not None:
        raise HTTPException(status_code=409, detail="This loom already has an active project")


async def _wif_path_for_project(draft: Draft, project_type: str | None) -> str:
    """Return the correct WIF path for a project type.

    For lift projects, prefer the liftplan-augmented file when available so
    """
    if project_type == "lift" and draft.wif_modified_path and await storage.afile_exists(draft.wif_modified_path):
        return draft.wif_modified_path
    return draft.wif_path  # type: ignore[return-value]


async def _get_owned_project(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    with_for_update: bool = False,
    allow_superuser: bool = False,
) -> Project:
    stmt = select(Project).where(
        Project.id == project_id,
        Project.deleted_at.is_(None),
    )
    if not (allow_superuser and user.is_superuser):
        stmt = stmt.where(Project.owner_id == user.id)
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


async def _load_sequence(project_id: uuid.UUID, db: AsyncSession) -> list[tuple[ProjectDraft, Draft]]:
    """Load the ordered draft sequence for a project with each entry's Draft record."""
    entries = (
        await db.scalars(
            select(ProjectDraft).where(ProjectDraft.project_id == project_id).order_by(ProjectDraft.position)
        )
    ).all()
    result: list[tuple[ProjectDraft, Draft]] = []
    for entry in entries:
        draft = await db.get(Draft, entry.draft_id)
        if draft is not None:
            result.append((entry, draft))
    return result


async def _sequence_detail(project: Project, project_id: uuid.UUID, db: AsyncSession) -> ProjectDetail:
    """Load sequence + loom + loom_version and return the standard detail response."""
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, sequence, loom, loom_version=loom_version)


def _active_pair(project: Project, sequence: list[tuple[ProjectDraft, Draft]]) -> tuple[ProjectDraft, Draft] | None:
    """Return the (entry, draft) for project.current_position, or position 1 as fallback."""
    for entry, draft in sequence:
        if entry.position == project.current_position:
            return entry, draft
    return sequence[0] if sequence else None


def _compute_total_picks(sequence: list[tuple[ProjectDraft, Draft]]) -> int:
    return sum((d.weft_threads or 0) * e.repeats for e, d in sequence)


def _compute_aggregate_current_pick(sequence: list[tuple[ProjectDraft, Draft]]) -> int:
    return sum(e.current_pick for e, _ in sequence)


def _build_sequence_schema(
    sequence: list[tuple[ProjectDraft, Draft]], current_position: int
) -> list[ProjectDraftSchema]:
    result = []
    for entry, draft in sequence:
        total = draft.weft_threads or 0
        result.append(
            ProjectDraftSchema(
                id=entry.id,
                draft_id=entry.draft_id,
                position=entry.position,
                repeats=entry.repeats,
                current_pick=entry.current_pick,
                draft_name=draft.name,
                draft_total_picks=total,
                section_total_picks=total * entry.repeats,
                is_active=entry.position == current_position,
                has_treadling=draft.has_treadling,
                has_liftplan=draft.has_liftplan,
            )
        )
    return result


def _yarn_color_schema(pyc: ProjectYarnColor) -> ProjectYarnColorSchema:
    yarn = pyc.yarn
    return ProjectYarnColorSchema(
        id=pyc.id,
        project_id=pyc.project_id,
        yarn_id=pyc.yarn_id,
        color_hex=pyc.color_hex,
        use_yarn_photo=pyc.use_yarn_photo,
        yarn_brand=yarn.brand if yarn else None,
        yarn_name=yarn.name if yarn else None,
        yarn_color_name=yarn.color_name if yarn else None,
        yarn_color_hex=yarn.color_hex if yarn else None,
        yarn_has_photo=yarn.photo_path is not None if yarn else False,
    )


def _active_draft_kwargs(active_draft: Draft | None, active_entry: ProjectDraft | None) -> dict:
    if active_draft is None:
        return {
            "current_pick": 0,
            "draft_name": None,
            "draft_num_shafts": None,
            "draft_num_treadles": None,
            "draft_effective_num_treadles": None,
            "draft_effective_num_shafts": None,
            "draft_metadata_overrides": None,
            "draft_wif_colors": None,
            "draft_warp_color_stats": None,
            "draft_weft_color_stats": None,
            "draft_wif_measurements": None,
            "draft_warp_threads": None,
            "draft_weft_threads": None,
            "draft_warp_length_cm": None,
            "draft_weaving_width_override_cm": None,
            "draft_epi_override": None,
        }
    return {
        "current_pick": active_entry.current_pick if active_entry else 0,
        "draft_name": active_draft.name,
        "draft_num_shafts": active_draft.num_shafts,
        "draft_num_treadles": active_draft.num_treadles,
        "draft_effective_num_treadles": active_draft.effective_num_treadles,
        "draft_effective_num_shafts": active_draft.effective_num_shafts,
        "draft_metadata_overrides": active_draft.metadata_overrides,
        "draft_wif_colors": active_draft.wif_colors,
        "draft_warp_color_stats": active_draft.warp_color_stats,
        "draft_weft_color_stats": active_draft.weft_color_stats,
        "draft_wif_measurements": active_draft.wif_measurements,
        "draft_warp_threads": active_draft.warp_threads,
        "draft_weft_threads": active_draft.weft_threads,
        "draft_warp_length_cm": active_draft.warp_length_cm,
        "draft_weaving_width_override_cm": active_draft.weaving_width_override_cm,
        "draft_epi_override": active_draft.epi_override,
    }


def _loom_kwargs(loom: Loom | None, loom_version: LoomVersion | None) -> dict:
    if loom is None:
        return {
            "loom_name": None,
            "loom_num_treadles": None,
            "loom_num_shafts": None,
            "loom_warp_waste_allowance": None,
            "loom_warp_waste_unit": None,
            "loom_resolved_version_id": None,
        }
    return {
        "loom_name": f"{loom.manufacturer} {loom.model_name}",
        "loom_num_treadles": loom_version.num_treadles if loom_version else None,
        "loom_num_shafts": loom_version.num_shafts if loom_version else None,
        "loom_warp_waste_allowance": loom_version.warp_waste_allowance if loom_version else None,
        "loom_warp_waste_unit": loom_version.warp_waste_unit if loom_version else None,
        "loom_resolved_version_id": loom_version.id if loom_version else None,
    }


def _to_detail(
    project: Project,
    sequence: list[tuple[ProjectDraft, Draft]],
    loom: Loom | None,
    photos: list[ProjectPhoto] | None = None,
    loom_version: LoomVersion | None = None,
    loom_reeds: list[dict] | None = None,
    yarn_colors: list[ProjectYarnColor] | None = None,
) -> ProjectDetail:
    active = _active_pair(project, sequence)
    active_entry = active[0] if active else None
    active_draft = active[1] if active else None

    total_picks = _compute_total_picks(sequence)
    agg_current = _compute_aggregate_current_pick(sequence)
    primary_draft_id = sequence[0][0].draft_id if sequence else None

    return ProjectDetail(
        id=project.id,
        owner_id=project.owner_id,
        loom_id=project.loom_id,
        loom_version_id=project.loom_version_id,
        name=project.name,
        project_type=project.project_type,
        status=project.status,
        current_position=project.current_position,
        current_item=project.current_item,
        num_items=project.num_items,
        length_unit=project.length_unit,
        total_picks=total_picks,
        aggregate_current_pick=agg_current,
        draft_id=primary_draft_id,
        draft_count=len(sequence),
        draft_sequence=_build_sequence_schema(sequence, project.current_position),
        finished_length_per_item=project.finished_length_per_item,
        waste_between_items=project.waste_between_items,
        warp_waste_allowance=project.warp_waste_allowance,
        completed_at=project.completed_at,
        abandoned_at=project.abandoned_at,
        notes=project.notes,
        created_at=project.created_at,
        hide_unused_shafts_treadles=project.hide_unused_shafts_treadles,
        color_replacements=project.color_replacements,
        has_drawdown_preview=project.drawdown_preview_path is not None,
        has_drawdown_svg=project.drawdown_svg_path is not None,
        share_slug=project.share_slug,
        share_visibility=project.share_visibility,
        share_expires_at=project.share_expires_at,
        reed_dents_per_inch=project.reed_dents_per_inch,
        tags=project.tags or [],
        loom_reeds=loom_reeds or [],
        photos=[ProjectPhotoSchema.model_validate(p) for p in (photos or [])],
        yarn_colors=[_yarn_color_schema(yc) for yc in (yarn_colors or [])],
        **_active_draft_kwargs(active_draft, active_entry),
        **_loom_kwargs(loom, loom_version),
    )


def _to_summary(
    project: Project,
    sequence: list[tuple[ProjectDraft, Draft]],
) -> ProjectSummary:
    active = _active_pair(project, sequence)
    active_entry = active[0] if active else None
    total_picks = _compute_total_picks(sequence)
    agg_current = _compute_aggregate_current_pick(sequence)
    primary_draft_id = sequence[0][0].draft_id if sequence else None

    return ProjectSummary(
        id=project.id,
        owner_id=project.owner_id,
        loom_id=project.loom_id,
        loom_version_id=project.loom_version_id,
        name=project.name,
        project_type=project.project_type,
        status=project.status,
        current_position=project.current_position,
        current_pick=active_entry.current_pick if active_entry else 0,
        current_item=project.current_item,
        num_items=project.num_items,
        length_unit=project.length_unit,
        total_picks=total_picks,
        aggregate_current_pick=agg_current,
        draft_id=primary_draft_id,
        draft_count=len(sequence),
        draft_sequence=_build_sequence_schema(sequence, project.current_position),
        completed_at=project.completed_at,
        abandoned_at=project.abandoned_at,
        created_at=project.created_at,
        hide_unused_shafts_treadles=project.hide_unused_shafts_treadles,
        has_drawdown_preview=project.drawdown_preview_path is not None,
        has_drawdown_svg=project.drawdown_svg_path is not None,
        share_slug=project.share_slug,
        share_visibility=project.share_visibility,
        share_expires_at=project.share_expires_at,
        tags=project.tags or [],
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
    if body.loom_version_id and not body.loom_id:
        raise HTTPException(status_code=400, detail="loom_version_id requires loom_id")

    loom: Loom | None = None
    project_type: str | None = None
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

        supports_lift, supports_treadle = loom_tracking_flags(loom.loom_type)
        if supports_lift:
            project_type = "lift"
        elif supports_treadle:
            project_type = "treadle"

    project = Project(
        owner_id=current_user.id,
        loom_id=body.loom_id,
        loom_version_id=body.loom_version_id,
        name=body.name,
        project_type=project_type,
        status="created",
        current_position=1,
        finished_length_per_item=body.finished_length_per_item,
        num_items=body.num_items,
        waste_between_items=body.waste_between_items,
        warp_waste_allowance=body.warp_waste_allowance,
        length_unit=body.length_unit,
        hide_unused_shafts_treadles=current_user.hide_unused_shafts_treadles,
        tags=[t.strip().lower() for t in body.tags if t.strip()],
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return _to_detail(project, [], loom)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    loom_id: uuid.UUID | None = Query(None),
    tags: list[str] | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    q = (
        select(Project)
        .where(Project.owner_id == current_user.id, Project.deleted_at.is_(None))
        .options(selectinload(Project.draft_sequence))
    )
    if loom_id is not None:
        q = q.where(Project.loom_id == loom_id)
    result = await db.scalars(q.order_by(Project.created_at.desc()))
    projects = result.all()

    summaries: list[ProjectSummary] = []
    for p in projects:
        # Build lightweight sequence (no draft details needed for list)
        seq: list[tuple[ProjectDraft, Draft]] = []
        for entry in sorted(p.draft_sequence, key=lambda e: e.position):
            draft = await db.get(Draft, entry.draft_id)
            if draft is not None:
                seq.append((entry, draft))
        summary = _to_summary(p, seq)
        if tags and not any(t in (p.tags or []) for t in tags):
            continue
        summaries.append(summary)
    return summaries


_SEQ_ENTRY_NOT_FOUND = "Sequence entry not found"
_NO_DRAFT_SEQUENCE = "Project has no draft sequence"
_SEQ_LOCKED = "Cannot modify sequence of an active or completed project"

# ---------------------------------------------------------------------------
# Sequence management
# ---------------------------------------------------------------------------


@router.post("/{project_id}/sequence", status_code=201)
async def add_sequence_entry(
    project_id: uuid.UUID,
    body: AddSequenceEntryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created",):
        raise HTTPException(status_code=400, detail=_SEQ_LOCKED)

    draft = await db.scalar(
        select(Draft).where(
            Draft.id == body.draft_id,
            Draft.owner_id == current_user.id,
            Draft.deleted_at.is_(None),
        )
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if body.repeats < 1:
        raise HTTPException(status_code=400, detail="repeats must be at least 1")

    # Find next position
    existing = (
        await db.scalars(
            select(ProjectDraft)
            .where(ProjectDraft.project_id == project_id)
            .order_by(ProjectDraft.position.desc())
            .limit(1)
        )
    ).first()
    next_position = (existing.position + 1) if existing else 1

    entry = ProjectDraft(
        project_id=project_id,
        draft_id=body.draft_id,
        position=next_position,
        repeats=body.repeats,
        current_pick=0,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(project)

    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)

    if draft.drawdown_preview_path is None:
        generate_drawdown_preview.delay(str(draft.id))

    return _to_detail(project, sequence, loom, loom_version=loom_version)


@router.patch("/{project_id}/sequence/{seq_id}")
async def update_sequence_entry(
    project_id: uuid.UUID,
    seq_id: uuid.UUID,
    body: UpdateSequenceEntryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)

    entry = await db.scalar(
        select(ProjectDraft).where(ProjectDraft.id == seq_id, ProjectDraft.project_id == project_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=_SEQ_ENTRY_NOT_FOUND)

    if body.repeats is not None:
        if body.repeats < 1:
            raise HTTPException(status_code=400, detail="repeats must be at least 1")
        entry.repeats = body.repeats

    await db.commit()
    await db.refresh(project)

    return await _sequence_detail(project, project_id, db)


@router.delete("/{project_id}/sequence/{seq_id}")
async def remove_sequence_entry(
    project_id: uuid.UUID,
    seq_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created",):
        raise HTTPException(status_code=400, detail=_SEQ_LOCKED)

    entry = await db.scalar(
        select(ProjectDraft).where(ProjectDraft.id == seq_id, ProjectDraft.project_id == project_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=_SEQ_ENTRY_NOT_FOUND)

    removed_position = entry.position
    await db.delete(entry)
    await db.flush()  # ensure DELETE is visible before renumbering

    # Re-number remaining entries to keep positions dense
    remaining = (
        await db.scalars(
            select(ProjectDraft)
            .where(ProjectDraft.project_id == project_id, ProjectDraft.position > removed_position)
            .order_by(ProjectDraft.position)
        )
    ).all()
    for i, rem in enumerate(remaining):
        rem.position = removed_position + i

    # Update current_position if it pointed to the removed entry
    if project.current_position >= removed_position:
        project.current_position = max(1, project.current_position - 1)

    await db.commit()
    await db.refresh(project)

    return await _sequence_detail(project, project_id, db)


@router.post("/{project_id}/sequence/reorder")
async def reorder_sequence(
    project_id: uuid.UUID,
    body: ReorderSequenceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created",):
        raise HTTPException(status_code=400, detail=_SEQ_LOCKED)

    entries = (await db.scalars(select(ProjectDraft).where(ProjectDraft.project_id == project_id))).all()
    entry_map = {e.id: e for e in entries}

    if set(body.ordered_ids) != set(entry_map.keys()):
        raise HTTPException(status_code=400, detail="ordered_ids must contain exactly all current sequence entry IDs")

    # Two-phase UPDATE to avoid unique constraint violations on position swaps.
    # Phase 1: negate all positions (no collisions since negatives ≠ positives).
    await db.execute(
        text("UPDATE project_drafts SET position = -position WHERE project_id = CAST(:project_id AS uuid)"),
        {"project_id": str(project_id)},
    )
    # Phase 2: set final positions one-by-one (no collisions since all are still negative).
    for new_pos, entry_id in enumerate(body.ordered_ids, start=1):
        await db.execute(
            text(
                "UPDATE project_drafts SET position = :pos, updated_at = now() "
                "WHERE id = CAST(:entry_id AS uuid) AND project_id = CAST(:project_id AS uuid)"
            ),
            {"pos": new_pos, "entry_id": str(entry_id), "project_id": str(project_id)},
        )

    # Expire all ORM objects so _load_sequence reads fresh DB state after raw SQL updates.
    db.expire_all()
    await db.commit()
    await db.refresh(project)

    return await _sequence_detail(project, project_id, db)


@router.post("/{project_id}/sequence/{seq_id}/activate")
async def activate_sequence_entry(
    project_id: uuid.UUID,
    seq_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    """Set the active sequence position (the one the pick tracker operates on)."""
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")

    entry = await db.scalar(
        select(ProjectDraft).where(ProjectDraft.id == seq_id, ProjectDraft.project_id == project_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=_SEQ_ENTRY_NOT_FOUND)

    project.current_position = entry.position
    await db.commit()
    await db.refresh(project)

    return await _sequence_detail(project, project_id, db)


# ---------------------------------------------------------------------------
# Drawdown endpoints (use active sequence position's draft)
# ---------------------------------------------------------------------------


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

    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = active

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
    _replacements = project.color_replacements or {}
    try:

        def _render_tile() -> tuple:
            d = rendering.load_draft(wif_bytes)
            if _replacements:
                rendering.apply_color_replacements(d, _replacements)
            return rendering.render_drawdown_tile(d, start_row=_sr, row_count=_rc, start_col=_sc, col_count=_cc)

        result = await asyncio.to_thread(_render_tile)
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


@router.get("/{project_id}/drawdown/svg")
async def get_project_drawdown_svg(
    project_id: uuid.UUID,
    cell_px: int = Query(20, ge=1, le=30),
    color_replacements: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    import json

    from app.services import rendering
    from app.services.storage import afile_exists, aread_file

    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = active

    wif_path = await _wif_path_for_project(draft, project.project_type)
    if not wif_path or not await afile_exists(wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    replacements: dict[str, str] = {}
    if color_replacements:
        try:
            replacements = json.loads(color_replacements)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid color_replacements JSON")

    wif_bytes = await aread_file(wif_path)
    try:

        def _render() -> tuple:
            d = rendering.load_draft(wif_bytes)
            if replacements:
                rendering.apply_color_replacements(d, replacements)
            s = rendering.render_drawdown_svg(d, cell_px)
            return d, s

        wif_draft, svg = await asyncio.to_thread(_render)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"SVG rendering failed: {exc}") from exc

    return Response(
        content=svg,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "X-Pixels-Per-Row": str(cell_px),
            "X-Total-Rows": str(len(wif_draft.weft)),
            "X-Total-Cols": str(len(wif_draft.warp)),
        },
    )


@router.get("/{project_id}/drawdown/preview")
async def get_project_drawdown_preview(
    project_id: uuid.UUID,
    color_replacements: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Full draft PNG (threading + tieup + drawdown), optionally with colour replacements applied."""
    import json

    from app.services import rendering
    from app.services.storage import afile_exists, aread_file

    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = active

    wif_path = await _wif_path_for_project(draft, project.project_type)
    if not wif_path or not await afile_exists(wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    replacements: dict[str, str] = {}
    if color_replacements:
        try:
            replacements = json.loads(color_replacements)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid color_replacements JSON")

    wif_bytes = await aread_file(wif_path)
    try:

        def _render() -> bytes:
            d = rendering.load_draft(wif_bytes)
            if replacements:
                rendering.apply_color_replacements(d, replacements)
            return rendering.render_full_draft(d)

        png_bytes = await asyncio.to_thread(_render)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview rendering failed: {exc}") from exc

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/{project_id}/drawdown_preview")
async def get_project_drawdown_preview_cached(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the pre-rendered drawdown thumbnail PNG for a project, or 404 if not yet generated."""
    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    if not project.drawdown_preview_path:
        raise HTTPException(status_code=404, detail="Preview not yet generated")
    data = await storage.aread_project_drawdown_preview(project.drawdown_preview_path)
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{project_id}/drawdown_svg")
async def get_project_drawdown_svg_cached(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the pre-rendered drawdown SVG for a project, or 404 if not yet generated."""
    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    if not project.drawdown_svg_path:
        raise HTTPException(status_code=404, detail="SVG not yet generated")
    svg_text = await storage.aread_project_drawdown_svg(project.drawdown_svg_path)
    return Response(
        content=svg_text,
        media_type="image/svg+xml; charset=utf-8",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{project_id}/drawdown/data")
async def get_project_drawdown_data(
    project_id: uuid.UUID,
    cell_px: int = Query(20, ge=4, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    from app.services import rendering
    from app.services.storage import afile_exists, aread_file

    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = active

    wif_path = await _wif_path_for_project(draft, project.project_type)
    if not wif_path or not await afile_exists(wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    wif_bytes = await aread_file(wif_path)
    try:

        def _render() -> tuple:
            d = rendering.load_draft(wif_bytes)
            if project.color_replacements:
                rendering.apply_color_replacements(d, project.color_replacements)
            data = rendering.render_drawdown_data(d, cell_px)
            return d, data

        wif_draft, payload = await asyncio.to_thread(_render)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drawdown data rendering failed: {exc}") from exc

    from fastapi.responses import JSONResponse

    return JSONResponse(
        content=payload,
        headers={
            "X-Pixels-Per-Row": str(cell_px),
            "X-Total-Rows": str(len(wif_draft.weft)),
            "X-Total-Cols": str(len(wif_draft.warp)),
        },
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    stmt = (
        select(Project)
        .where(Project.id == project_id, Project.deleted_at.is_(None))
        .options(
            selectinload(Project.photos),
            selectinload(Project.yarn_colors).selectinload(ProjectYarnColor.yarn),
        )
    )
    if not current_user.is_superuser:
        stmt = stmt.where(Project.owner_id == current_user.id)
    result = await db.scalars(stmt)
    project = result.first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is not None:
        _, active_draft = active
        if active_draft.drawdown_preview_path is None:
            generate_drawdown_preview.delay(str(active_draft.id))

    loom_reeds: list[dict] = []
    if project.loom_id:
        loom_stmt = select(Loom).where(Loom.id == project.loom_id).options(selectinload(Loom.reeds))
        loom = (await db.scalars(loom_stmt)).first()
        if loom:
            loom_reeds = [{"id": str(r.id), "dents_per_inch": r.dents_per_inch} for r in loom.reeds]
    else:
        loom = None
    loom_version = await _resolve_loom_version(project, db)

    return _to_detail(
        project,
        sequence,
        loom,
        photos=list(project.photos),
        loom_version=loom_version,
        loom_reeds=loom_reeds,
        yarn_colors=list(project.yarn_colors),
    )


@router.patch("/{project_id}", response_model=ProjectDetail)
async def rename_project(
    project_id: uuid.UUID,
    body: RenameProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.name is None and body.notes is None and body.hide_unused_shafts_treadles is None and body.tags is None:
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
    if body.tags is not None:
        project.tags = [t.strip().lower() for t in body.tags if t.strip()]
    await db.commit()
    await db.refresh(project)
    return await _sequence_detail(project, project_id, db)


@router.patch("/{project_id}/color-replacements", response_model=ProjectDetail)
async def set_color_replacements(
    project_id: uuid.UUID,
    body: ColorReplacementsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    import re as re_mod

    hex_re = re_mod.compile(r"^#[0-9a-fA-F]{6}$")
    for k, v in body.color_replacements.items():
        if not hex_re.match(k) or not hex_re.match(v):
            raise HTTPException(status_code=422, detail="color_replacements keys and values must be 6-digit hex colors")
    project = await _get_owned_project(project_id, current_user, db)
    project.color_replacements = body.color_replacements or None
    await db.commit()
    await db.refresh(project)
    prerender_project_tiles.delay(str(project_id))
    generate_project_drawdown_preview.delay(str(project_id))
    generate_project_drawdown_svg.delay(str(project_id))
    return await _sequence_detail(project, project_id, db)


@router.patch("/{project_id}/warp-setup", response_model=ProjectDetail)
async def update_warp_setup(
    project_id: uuid.UUID,
    body: WarpSetupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(status_code=400, detail="At least one field must be provided")
    if "num_items" in fields:
        if project.status != "created":
            raise HTTPException(status_code=400, detail="Items can only be changed before weaving starts")
        project.num_items = max(1, body.num_items)  # type: ignore[arg-type, type-var, assignment]
    if "finished_length_per_item" in fields:
        project.finished_length_per_item = body.finished_length_per_item
    if "waste_between_items" in fields:
        project.waste_between_items = body.waste_between_items
    if "warp_waste_allowance" in fields:
        project.warp_waste_allowance = body.warp_waste_allowance
    if "length_unit" in fields and body.length_unit in ("cm", "in"):
        project.length_unit = body.length_unit  # type: ignore[assignment]
    await db.commit()
    await db.refresh(project)
    return await _sequence_detail(project, project_id, db)


@router.patch("/{project_id}/reed", response_model=ProjectDetail)
async def set_reed(
    project_id: uuid.UUID,
    body: SetReedRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.reed_dents_per_inch is not None and body.reed_dents_per_inch <= 0:
        raise HTTPException(status_code=400, detail="reed_dents_per_inch must be positive")
    project = await _get_owned_project(project_id, current_user, db)
    project.reed_dents_per_inch = body.reed_dents_per_inch
    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom_reeds: list[dict] = []
    if project.loom_id:
        loom_stmt = select(Loom).where(Loom.id == project.loom_id).options(selectinload(Loom.reeds))
        loom = (await db.scalars(loom_stmt)).first()
        if loom:
            loom_reeds = [{"id": str(r.id), "dents_per_inch": r.dents_per_inch} for r in loom.reeds]
    else:
        loom = None
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, sequence, loom, loom_version=loom_version, loom_reeds=loom_reeds)


@router.post("/{project_id}/assign-loom", response_model=ProjectDetail)
async def assign_loom(
    project_id: uuid.UUID,
    body: AssignLoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
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

    # Derive project_type from loom — table_loom → lift, floor_loom → treadle
    supports_lift, supports_treadle = loom_tracking_flags(loom.loom_type)
    if supports_lift:
        project.project_type = "lift"
    elif supports_treadle:
        project.project_type = "treadle"

    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, sequence, loom, loom_version=loom_version)


def _validate_sequence_for_start(sequence: list[tuple[ProjectDraft, Draft]], project_type: str | None) -> None:
    for _entry, draft in sequence:
        if not (draft.weft_threads or 0):
            raise HTTPException(
                status_code=400,
                detail=f"Draft '{draft.name}' has no picks defined — cannot start tracking",
            )
        if project_type == "treadle" and not draft.has_treadling:
            raise HTTPException(
                status_code=400,
                detail=f"Draft '{draft.name}' is missing a treadling plan required for this loom",
            )
        if project_type == "lift" and not draft.has_liftplan:
            raise HTTPException(
                status_code=400,
                detail=f"Draft '{draft.name}' is missing a lift plan required for this loom",
            )


@router.post("/{project_id}/start", response_model=ProjectDetail)
async def start_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    """Validate all gates then transition a project from 'created' to 'active'."""
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Only projects in 'created' or 'active' status can be started")

    if project.status == "created":
        sequence = await _load_sequence(project_id, db)

        if not sequence:
            raise HTTPException(status_code=400, detail="Add at least one draft to the sequence before starting")
        if project.loom_id is None:
            raise HTTPException(status_code=400, detail="Assign a loom before starting")

        loom_conflict = await db.scalar(
            select(Project).where(
                Project.loom_id == project.loom_id,
                Project.owner_id == current_user.id,
                Project.status == "active",
                Project.deleted_at.is_(None),
                Project.id != project.id,
            )
        )
        if loom_conflict is not None:
            raise HTTPException(status_code=409, detail=f"Loom is in use by project '{loom_conflict.name}'")

        _validate_sequence_for_start(sequence, project.project_type)

        project.status = "active"
        await db.commit()
        await db.refresh(project)
    else:
        sequence = await _load_sequence(project_id, db)

    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)
    return _to_detail(project, sequence, loom, loom_version=loom_version)


@router.post("/{project_id}/step", response_model=StepResponse)
async def step_project(
    project_id: uuid.UUID,
    body: StepRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StepResponse:
    if body.direction not in ("advance", "reverse"):
        raise HTTPException(status_code=400, detail="direction must be 'advance' or 'reverse'")

    project = await _get_owned_project(project_id, current_user, db, with_for_update=True)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")
    if project.status == "created":
        project.status = "active"

    # Load and lock the active sequence entry
    seq_entry = await db.scalar(
        select(ProjectDraft)
        .where(
            ProjectDraft.project_id == project_id,
            ProjectDraft.position == project.current_position,
        )
        .with_for_update()
    )
    if seq_entry is None:
        raise HTTPException(status_code=400, detail="No active sequence entry — activate a sequence position first")

    draft = await db.get(Draft, seq_entry.draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    section_total = (draft.weft_threads or 0) * seq_entry.repeats
    from_pick = seq_entry.current_pick

    if body.direction == "advance":
        if seq_entry.current_pick >= section_total:
            raise HTTPException(status_code=400, detail="Already at last pick of this section")
        seq_entry.current_pick += 1
    else:
        if seq_entry.current_pick <= 0:
            raise HTTPException(status_code=400, detail="Already at first pick of this section")
        seq_entry.current_pick -= 1

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
        sequence_id=seq_entry.id,
        event_type=body.direction,
        from_pick=from_pick,
        to_pick=seq_entry.current_pick,
        dwell_ms=dwell_ms,
    )
    db.add(step)
    await db.commit()

    # Compute aggregates for response
    all_entries = (await db.scalars(select(ProjectDraft).where(ProjectDraft.project_id == project_id))).all()
    agg_drafts: list[tuple[ProjectDraft, Draft]] = []
    for e in all_entries:
        d = await db.get(Draft, e.draft_id)
        if d:
            agg_drafts.append((e, d))

    return StepResponse(
        current_pick=seq_entry.current_pick,
        total_picks=section_total,
        position=project.current_position,
        aggregate_current_pick=_compute_aggregate_current_pick(agg_drafts),
        aggregate_total_picks=_compute_total_picks(agg_drafts),
        current_item=project.current_item,
        num_items=project.num_items,
    )


@router.post("/{project_id}/jump", response_model=ProjectDetail)
async def jump_project(
    project_id: uuid.UUID,
    body: JumpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")

    seq_entry = await db.scalar(
        select(ProjectDraft).where(
            ProjectDraft.project_id == project_id,
            ProjectDraft.position == project.current_position,
        )
    )
    if seq_entry is None:
        raise HTTPException(status_code=400, detail="No active sequence entry")

    draft = await db.get(Draft, seq_entry.draft_id)
    section_total = (draft.weft_threads or 0) * seq_entry.repeats if draft else 0
    seq_entry.current_pick = max(0, min(body.pick, section_total))

    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, sequence, loom)


@router.post("/{project_id}/advance-item", response_model=StepResponse)
async def advance_item(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StepResponse:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")

    sequence = await _load_sequence(project_id, db)
    total_picks = _compute_total_picks(sequence)
    agg_current = _compute_aggregate_current_pick(sequence)

    if agg_current < total_picks:
        raise HTTPException(status_code=400, detail="Current sequence is not finished — complete all picks first")
    if project.current_item >= project.num_items:
        raise HTTPException(status_code=400, detail="Already on the last item — use complete instead")

    # Reset all sequence picks to 0 for the next item
    for entry, _ in sequence:
        entry.current_pick = 0
    project.current_item += 1
    await db.commit()

    return StepResponse(
        current_pick=0,
        total_picks=total_picks,
        position=project.current_position,
        aggregate_current_pick=0,
        aggregate_total_picks=total_picks,
        current_item=project.current_item,
        num_items=project.num_items,
    )


@router.post("/{project_id}/jump-item", response_model=ProjectDetail)
async def jump_item(
    project_id: uuid.UUID,
    body: JumpItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")
    target = max(1, min(body.item, project.num_items))
    project.current_item = target
    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, sequence, loom)


@router.post("/{project_id}/complete", response_model=ProjectDetail)
async def complete_project(
    project_id: uuid.UUID,
    force: bool = Query(False, description="Complete even if not all picks are logged"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")

    if not force:
        sequence = await _load_sequence(project_id, db)
        total_picks = _compute_total_picks(sequence)
        agg_current = _compute_aggregate_current_pick(sequence)
        if agg_current < total_picks:
            raise HTTPException(status_code=400, detail="Not all picks are done — advance to the last pick first")
        if project.current_item < project.num_items:
            raise HTTPException(status_code=400, detail="Not all items are done — advance to the last item first")

    project.status = "completed"
    project.completed_at = datetime.now(timezone.utc)
    await _close_open_session(project_id, db)
    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, sequence, loom)


@router.post("/{project_id}/abandon", response_model=ProjectDetail)
async def abandon_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    if project.status not in ("created", "active"):
        raise HTTPException(status_code=400, detail="Project is not active")
    project.status = "abandoned"
    project.abandoned_at = datetime.now(timezone.utc)
    await _close_open_session(project_id, db)
    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, sequence, loom)


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
    project.status = "created"
    await db.commit()
    await db.refresh(project)
    sequence = await _load_sequence(project_id, db)
    loom = await db.get(Loom, project.loom_id) if project.loom_id else None
    return _to_detail(project, sequence, loom)


@router.get("/{project_id}/metrics", response_model=ProjectMetricsResponse)
async def get_project_metrics(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectMetricsResponse:
    await _get_owned_project(project_id, current_user, db, allow_superuser=True)

    now = datetime.now(timezone.utc)

    sessions = (
        await db.scalars(
            select(WeaveSession).where(WeaveSession.project_id == project_id).order_by(WeaveSession.started_at)
        )
    ).all()

    steps = (await db.scalars(select(ProjectStep).where(ProjectStep.project_id == project_id))).all()

    total_advance = sum(1 for s in steps if s.event_type == "advance")
    total_reverse = sum(1 for s in steps if s.event_type == "reverse")

    worked_dwells = [
        s.dwell_ms
        for s in steps
        if s.event_type == "advance" and s.dwell_ms is not None and s.dwell_ms >= _WORKED_PICK_THRESHOLD_MS
    ]
    total_worked = len(worked_dwells)
    avg_pick_dwell_ms = int(sum(worked_dwells) / len(worked_dwells)) if worked_dwells else None

    total_session_ms = 0
    session_infos: list[SessionInfo] = []
    current_session_started_at: datetime | None = None
    for sess in sessions:
        end = sess.ended_at or now
        duration_ms = int((end - sess.started_at).total_seconds() * 1_000)
        total_session_ms += duration_ms
        step_count = sum(1 for s in steps if sess.started_at <= s.created_at <= end)
        session_infos.append(
            SessionInfo(
                id=sess.id,
                started_at=sess.started_at,
                ended_at=sess.ended_at,
                duration_ms=duration_ms,
                step_count=step_count,
            )
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
        avg_pick_dwell_ms=avg_pick_dwell_ms,
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
        loom_id=source.loom_id,
        loom_version_id=source.loom_version_id,
        name=source.name,
        project_type=source.project_type,
        status="created",
        current_position=1,
        finished_length_per_item=source.finished_length_per_item,
        num_items=source.num_items,
        waste_between_items=source.waste_between_items,
        warp_waste_allowance=source.warp_waste_allowance,
        length_unit=source.length_unit,
    )
    db.add(clone)
    await db.flush()

    # Clone the sequence
    source_sequence = await _load_sequence(project_id, db)
    for entry, draft in source_sequence:
        cloned_entry = ProjectDraft(
            project_id=clone.id,
            draft_id=entry.draft_id,
            position=entry.position,
            repeats=entry.repeats,
            current_pick=0,
        )
        db.add(cloned_entry)

    await db.commit()
    await db.refresh(clone)
    clone_sequence = await _load_sequence(clone.id, db)
    loom = await db.get(Loom, clone.loom_id) if clone.loom_id else None
    return _to_detail(clone, clone_sequence, loom)


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

    try:
        validate_image_format(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
    await _get_owned_project(project_id, current_user, db, allow_superuser=True)
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
    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    if project.project_type is None:
        raise HTTPException(status_code=400, detail="Project has no type set — assign a loom first")

    sequence = await _load_sequence(project_id, db)
    active = _active_pair(project, sequence)
    if active is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = active

    wif_bytes = await storage.aread_file(await _wif_path_for_project(draft, project.project_type))
    try:
        pick_data = await asyncio.to_thread(wif_parser.parse_picks, wif_bytes, project.project_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    replacements = {k.lower(): v for k, v in (project.color_replacements or {}).items()}

    def _apply(color: str | None) -> str | None:
        return replacements.get(color.lower(), color) if color else None

    pick_rows = [
        PickRow(pick=i + 1, active=row, color=_apply(pick_data.weft_colors[i])) for i, row in enumerate(pick_data.picks)
    ]
    return PicksResponse(
        project_type=pick_data.project_type,
        total_picks=pick_data.total_picks,
        picks=pick_rows,
        has_weft_colors=any(p.color is not None for p in pick_rows),
    )


def _compute_color_runs(entries: list[dict]) -> list[WarpingPlanColorRun]:
    if not entries:
        return []
    runs: list[WarpingPlanColorRun] = []
    cur_color = entries[0]["color"]
    cur_name = entries[0].get("color_name")
    start = entries[0]["end"]
    count = 1
    for entry in entries[1:]:
        if entry["color"] == cur_color:
            count += 1
        else:
            runs.append(
                WarpingPlanColorRun(
                    color=cur_color, color_name=cur_name, start_end=start, end_end=start + count - 1, count=count
                )
            )
            cur_color = entry["color"]
            cur_name = entry.get("color_name")
            start = entry["end"]
            count = 1
    runs.append(
        WarpingPlanColorRun(
            color=cur_color, color_name=cur_name, start_end=start, end_end=start + count - 1, count=count
        )
    )
    return runs


async def _parse_wif_for_warping_plan(
    wif_bytes: bytes, has_threading: bool
) -> tuple[
    list[WarpingPlanEndEntry] | None,
    list[WarpingPlanColorRun] | None,
    list[list[int]] | None,
    int | None,
    int | None,
]:
    threading_entries: list[WarpingPlanEndEntry] | None = None
    warp_color_runs: list[WarpingPlanColorRun] | None = None
    tieup_data: list[list[int]] | None = None
    tieup_num_shafts: int | None = None
    tieup_num_treadles: int | None = None

    if has_threading:
        try:
            t_data = await asyncio.to_thread(wif_parser.parse_threading, wif_bytes)
            raw_entries = [
                {
                    "end": i + 1,
                    "shafts": shafts,
                    "color": t_data.warp_colors[i],
                    "color_name": t_data.color_names.get(t_data.warp_colors[i]) if t_data.warp_colors[i] else None,  # type: ignore[arg-type]
                }
                for i, shafts in enumerate(t_data.threading)
            ]
            threading_entries = [WarpingPlanEndEntry(**e) for e in raw_entries]  # type: ignore[arg-type]
            warp_color_runs = _compute_color_runs(raw_entries)
        except ValueError:
            pass

    try:
        tu = await asyncio.to_thread(wif_parser.parse_tieup, wif_bytes)
        tieup_data = tu.tieup
        tieup_num_shafts = tu.num_shafts
        tieup_num_treadles = tu.num_treadles
    except ValueError:
        pass

    return threading_entries, warp_color_runs, tieup_data, tieup_num_shafts, tieup_num_treadles


def _compute_epi(draft: Draft) -> float | None:
    if draft.epi_override is not None:
        return draft.epi_override
    if draft.wif_measurements:
        spacing = draft.wif_measurements.get("warp_spacing")
        if spacing and spacing > 0:
            return round(2.54 / float(spacing), 1)
    return None


@router.get("/{project_id}/warping-plan", response_model=WarpingPlanResponse)
async def get_warping_plan(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WarpingPlanResponse:
    project = await _get_owned_project(project_id, current_user, db, allow_superuser=True)
    sequence = await _load_sequence(project_id, db)
    # Warping plan uses position-1 draft (primary warp reference)
    primary = sequence[0] if sequence else None
    if primary is None:
        raise HTTPException(status_code=404, detail=_NO_DRAFT_SEQUENCE)
    _, draft = primary

    threading_entries = warp_color_runs = tieup_data = tieup_num_shafts = tieup_num_treadles = None
    wif_path = await _wif_path_for_project(draft, project.project_type)
    if wif_path and await storage.afile_exists(wif_path):
        wif_bytes = await storage.aread_file(wif_path)
        (
            threading_entries,
            warp_color_runs,
            tieup_data,
            tieup_num_shafts,
            tieup_num_treadles,
        ) = await _parse_wif_for_warping_plan(wif_bytes, bool(draft.has_threading))

    return WarpingPlanResponse(
        project_id=project.id,
        draft_name=draft.name,
        project_type=project.project_type,
        warp_threads=draft.warp_threads,
        total_picks=draft.weft_threads,
        num_shafts=draft.effective_num_shafts or draft.num_shafts,
        num_treadles=draft.effective_num_treadles or draft.num_treadles,
        warp_color_summary=draft.warp_color_stats or [],
        weft_color_summary=draft.weft_color_stats or [],
        threading=threading_entries,
        warp_color_runs=warp_color_runs,
        warp_length_cm=draft.warp_length_cm,
        epi=_compute_epi(draft),
        has_threading=bool(draft.has_threading),
        tieup=tieup_data,
        tieup_num_shafts=tieup_num_shafts,
        tieup_num_treadles=tieup_num_treadles,
        has_tieup=tieup_data is not None,
    )


# ---------------------------------------------------------------------------
# Share endpoints (owner)
# ---------------------------------------------------------------------------


@router.patch("/{project_id}/share", response_model=ProjectDetail)
async def update_project_share(
    project_id: uuid.UUID,
    body: ShareProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.visibility != "link":
        raise HTTPException(status_code=400, detail="visibility must be 'link'")

    project = await _get_owned_project(project_id, current_user, db, with_for_update=True)
    sequence = await _load_sequence(project_id, db)
    if not sequence:
        raise HTTPException(status_code=400, detail="Cannot share a project with no drafts")

    if project.share_slug is None:
        project.share_slug = await _generate_unique_slug(project.name, db)

    project.share_visibility = body.visibility
    project.share_expires_at = body.expires_at

    await db.commit()
    await db.refresh(project)

    loom: Loom | None = await db.get(Loom, project.loom_id) if project.loom_id else None
    loom_version = await _resolve_loom_version(project, db)
    photos = list(
        await db.scalars(
            select(ProjectPhoto).where(ProjectPhoto.project_id == project.id).order_by(ProjectPhoto.display_order)
        )
    )
    return _to_detail(project, sequence, loom, photos, loom_version)


@router.delete("/{project_id}/share", status_code=204)
async def revoke_project_share(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await _get_owned_project(project_id, current_user, db, with_for_update=True)
    project.share_slug = None
    project.share_visibility = "private"
    project.share_expires_at = None
    await db.commit()


# ---------------------------------------------------------------------------
# Public share endpoint (no auth)
# ---------------------------------------------------------------------------


def _shared_draft_fields(active_draft: Draft | None, active_entry: ProjectDraft | None) -> dict:
    if active_draft is None:
        return {
            "draft_name": None,
            "draft_num_shafts": None,
            "draft_num_treadles": None,
            "current_pick": 0,
            "draft_wif_colors": None,
            "draft_warp_color_stats": None,
            "draft_weft_color_stats": None,
        }
    return {
        "draft_name": active_draft.name,
        "draft_num_shafts": active_draft.effective_num_shafts or active_draft.num_shafts,
        "draft_num_treadles": active_draft.effective_num_treadles or active_draft.num_treadles,
        "current_pick": active_entry.current_pick if active_entry else 0,
        "draft_wif_colors": active_draft.wif_colors,
        "draft_warp_color_stats": active_draft.warp_color_stats,
        "draft_weft_color_stats": active_draft.weft_color_stats,
    }


@share_router.get("/projects/{slug}", response_model=SharedProjectResponse)
async def get_shared_project(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> SharedProjectResponse:
    project = await db.scalar(
        select(Project).where(
            Project.share_slug == slug,
            Project.deleted_at.is_(None),
        )
    )
    if project is None or project.share_visibility == "private":
        raise HTTPException(status_code=404, detail="Shared project not found")

    now = datetime.now(timezone.utc)
    if project.share_expires_at is not None and project.share_expires_at <= now:
        raise HTTPException(status_code=410, detail="This share link has expired")

    sequence = await _load_sequence(project.id, db)
    active = _active_pair(project, sequence)

    from app.models.user import User as UserModel

    owner = await db.get(UserModel, project.owner_id)
    owner_display = owner.display_name if owner and owner.display_name else "Unknown"

    return SharedProjectResponse(
        slug=slug,
        project_name=project.name,
        project_status=project.status,
        project_type=project.project_type,
        owner_display_name=owner_display,
        num_items=project.num_items,
        total_picks=_compute_total_picks(sequence),
        current_item=project.current_item,
        share_visibility=project.share_visibility,
        share_expires_at=project.share_expires_at,
        created_at=project.created_at,
        completed_at=project.completed_at,
        abandoned_at=project.abandoned_at,
        has_drawdown_preview=project.drawdown_preview_path is not None,
        has_drawdown_svg=project.drawdown_svg_path is not None,
        color_replacements=project.color_replacements,
        **_shared_draft_fields(active[1] if active else None, active[0] if active else None),
    )


@share_router.get("/projects/{slug}/preview")
async def get_shared_project_preview(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the pre-rendered drawdown preview PNG for a shared project (no auth required)."""
    project = await db.scalar(select(Project).where(Project.share_slug == slug, Project.deleted_at.is_(None)))
    if project is None or project.share_visibility == "private":
        raise HTTPException(status_code=404, detail="Not found")
    now = datetime.now(timezone.utc)
    if project.share_expires_at is not None and project.share_expires_at <= now:
        raise HTTPException(status_code=410, detail="Expired")
    if not project.drawdown_preview_path:
        raise HTTPException(status_code=404, detail="Preview not yet generated")
    data = await storage.aread_project_drawdown_preview(project.drawdown_preview_path)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})


@share_router.get("/projects/{slug}/svg")
async def get_shared_project_svg(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return the pre-rendered drawdown SVG for a shared project (no auth required)."""
    project = await db.scalar(select(Project).where(Project.share_slug == slug, Project.deleted_at.is_(None)))
    if project is None or project.share_visibility == "private":
        raise HTTPException(status_code=404, detail="Not found")
    now = datetime.now(timezone.utc)
    if project.share_expires_at is not None and project.share_expires_at <= now:
        raise HTTPException(status_code=410, detail="Expired")
    if not project.drawdown_svg_path:
        raise HTTPException(status_code=404, detail="SVG not yet generated")
    svg_text = await storage.aread_project_drawdown_svg(project.drawdown_svg_path)
    return Response(
        content=svg_text,
        media_type="image/svg+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ---------------------------------------------------------------------------
# Yarn-color linking endpoints
# ---------------------------------------------------------------------------


class LinkYarnColorRequest(BaseModel):
    yarn_id: uuid.UUID
    color_hex: str
    use_yarn_photo: bool = False


class PatchYarnColorRequest(BaseModel):
    use_yarn_photo: bool


@router.get("/{project_id}/yarn-colors")
async def list_project_yarn_colors(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProjectYarnColorSchema]:
    await _get_owned_project(project_id, current_user, db)
    stmt = (
        select(ProjectYarnColor)
        .where(ProjectYarnColor.project_id == project_id)
        .options(selectinload(ProjectYarnColor.yarn))
        .order_by(ProjectYarnColor.color_hex)
    )
    rows = (await db.scalars(stmt)).all()
    return [_yarn_color_schema(r) for r in rows]


@router.put("/{project_id}/yarn-colors/{color_hex}", status_code=200)
async def link_yarn_color(
    project_id: uuid.UUID,
    color_hex: str,
    body: LinkYarnColorRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectYarnColorSchema:
    await _get_owned_project(project_id, current_user, db)
    yarn = await db.scalar(
        select(Yarn).where(Yarn.id == body.yarn_id, Yarn.owner_id == current_user.id, Yarn.deleted_at.is_(None))
    )
    if yarn is None:
        raise HTTPException(status_code=404, detail="Yarn not found")
    existing = await db.scalar(
        select(ProjectYarnColor).where(
            ProjectYarnColor.project_id == project_id,
            ProjectYarnColor.color_hex == color_hex,
        )
    )
    if existing is not None:
        existing.yarn_id = body.yarn_id
        existing.use_yarn_photo = body.use_yarn_photo
        await db.commit()
        await db.refresh(existing)
        existing.yarn = yarn
        return _yarn_color_schema(existing)
    row = ProjectYarnColor(
        project_id=project_id,
        yarn_id=body.yarn_id,
        color_hex=color_hex,
        use_yarn_photo=body.use_yarn_photo,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    row.yarn = yarn
    return _yarn_color_schema(row)


@router.patch("/{project_id}/yarn-colors/{color_hex}")
async def patch_yarn_color(
    project_id: uuid.UUID,
    color_hex: str,
    body: PatchYarnColorRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectYarnColorSchema:
    await _get_owned_project(project_id, current_user, db)
    row = await db.scalar(
        select(ProjectYarnColor)
        .where(ProjectYarnColor.project_id == project_id, ProjectYarnColor.color_hex == color_hex)
        .options(selectinload(ProjectYarnColor.yarn))
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Yarn color assignment not found")
    row.use_yarn_photo = body.use_yarn_photo
    await db.commit()
    await db.refresh(row)
    return _yarn_color_schema(row)


@router.delete("/{project_id}/yarn-colors/{color_hex}", status_code=204)
async def unlink_yarn_color(
    project_id: uuid.UUID,
    color_hex: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await _get_owned_project(project_id, current_user, db)
    row = await db.scalar(
        select(ProjectYarnColor).where(
            ProjectYarnColor.project_id == project_id,
            ProjectYarnColor.color_hex == color_hex,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Yarn color assignment not found")
    await db.delete(row)
    await db.commit()
