import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.activity import Activity, ActivityStep
from app.models.loom import Loom, LoomVersion
from app.models.project import Project
from app.models.user import User
from app.services import storage, wif_parser

router = APIRouter(prefix="/api/activities", tags=["activities"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActivitySummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    loom_id: uuid.UUID | None
    loom_version_id: uuid.UUID | None
    name: str
    activity_type: str
    status: str
    current_pick: int
    total_picks: int
    num_items: int
    length_unit: str
    completed_at: datetime | None
    abandoned_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityDetail(ActivitySummary):
    finished_length_per_item: Decimal | None
    waste_between_items: Decimal | None
    warp_waste_allowance: Decimal | None
    completed_at: datetime | None
    notes: str | None
    project_name: str
    project_num_shafts: int | None
    project_num_treadles: int | None
    loom_name: str | None


class CreateActivityRequest(BaseModel):
    name: str
    project_id: uuid.UUID
    activity_type: str  # "treadle" | "lift"
    loom_id: uuid.UUID | None = None
    loom_version_id: uuid.UUID | None = None
    finished_length_per_item: Decimal | None = None
    num_items: int = 1
    waste_between_items: Decimal | None = None
    warp_waste_allowance: Decimal | None = None
    length_unit: str = "cm"


class RenameActivityRequest(BaseModel):
    name: str


class AssignLoomRequest(BaseModel):
    loom_id: uuid.UUID
    loom_version_id: uuid.UUID | None = None


class JumpRequest(BaseModel):
    pick: int


class StepRequest(BaseModel):
    direction: str  # "advance" | "reverse"


class PickRow(BaseModel):
    pick: int
    active: list[int]
    color: str | None = None  # hex weft color e.g. "#ff0000", None if not defined


class PicksResponse(BaseModel):
    activity_type: str
    total_picks: int
    picks: list[PickRow]
    has_weft_colors: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _check_loom_conflict(
    loom_id: uuid.UUID, exclude_id: uuid.UUID | None, owner_id: uuid.UUID, db: AsyncSession
) -> None:
    """Raise 409 if the loom already has an active activity (other than exclude_id)."""
    q = select(Activity).where(
        Activity.loom_id == loom_id,
        Activity.owner_id == owner_id,
        Activity.status == "active",
        Activity.deleted_at.is_(None),
    )
    if exclude_id is not None:
        q = q.where(Activity.id != exclude_id)
    if await db.scalar(q) is not None:
        raise HTTPException(status_code=409, detail="This loom already has an active activity")


async def _get_owned_activity(activity_id: uuid.UUID, user: User, db: AsyncSession) -> Activity:
    activity = await db.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.owner_id == user.id,
            Activity.deleted_at.is_(None),
        )
    )
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


def _to_detail(activity: Activity, project: Project, loom: Loom | None) -> ActivityDetail:
    return ActivityDetail(
        id=activity.id,
        project_id=activity.project_id,
        loom_id=activity.loom_id,
        loom_version_id=activity.loom_version_id,
        name=activity.name,
        activity_type=activity.activity_type,
        status=activity.status,
        current_pick=activity.current_pick,
        total_picks=activity.total_picks,
        finished_length_per_item=activity.finished_length_per_item,
        num_items=activity.num_items,
        waste_between_items=activity.waste_between_items,
        warp_waste_allowance=activity.warp_waste_allowance,
        length_unit=activity.length_unit,
        completed_at=activity.completed_at,
        abandoned_at=activity.abandoned_at,
        notes=activity.notes,
        created_at=activity.created_at,
        project_name=project.name,
        project_num_shafts=project.num_shafts,
        project_num_treadles=project.num_treadles,
        loom_name=f"{loom.manufacturer} {loom.model_name}" if loom else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ActivityDetail, status_code=201)
async def create_activity(
    body: CreateActivityRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    if body.activity_type not in ("treadle", "lift"):
        raise HTTPException(status_code=400, detail="activity_type must be 'treadle' or 'lift'")

    project = await db.scalar(
        select(Project).where(
            Project.id == body.project_id,
            Project.owner_id == current_user.id,
            Project.deleted_at.is_(None),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate activity type is supported by the WIF
    if body.activity_type == "treadle" and not project.has_treadling:
        raise HTTPException(status_code=400, detail="WIF file has no [TREADLING] section")
    if body.activity_type == "lift" and not project.has_liftplan:
        raise HTTPException(status_code=400, detail="WIF file has no [LIFTPLAN] section")

    # Parse pick count from WIF
    wif_bytes = storage.read_file(project.wif_path)
    try:
        pick_data = wif_parser.parse_picks(wif_bytes, body.activity_type)
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

    activity = Activity(
        owner_id=current_user.id,
        project_id=body.project_id,
        loom_id=body.loom_id,
        loom_version_id=body.loom_version_id,
        name=body.name,
        activity_type=body.activity_type,
        status="active",
        current_pick=1,
        total_picks=pick_data.total_picks,
        finished_length_per_item=body.finished_length_per_item,
        num_items=body.num_items,
        waste_between_items=body.waste_between_items,
        warp_waste_allowance=body.warp_waste_allowance,
        length_unit=body.length_unit,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return _to_detail(activity, project, loom)


@router.get("", response_model=list[ActivitySummary])
async def list_activities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActivitySummary]:
    result = await db.scalars(
        select(Activity)
        .where(Activity.owner_id == current_user.id, Activity.deleted_at.is_(None))
        .order_by(Activity.created_at.desc())
    )
    return [ActivitySummary.model_validate(a) for a in result.all()]


@router.get("/{activity_id}", response_model=ActivityDetail)
async def get_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.patch("/{activity_id}", response_model=ActivityDetail)
async def rename_activity(
    activity_id: uuid.UUID,
    body: RenameActivityRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    activity = await _get_owned_activity(activity_id, current_user, db)
    activity.name = name
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/assign-loom", response_model=ActivityDetail)
async def assign_loom(
    activity_id: uuid.UUID,
    body: AssignLoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "active":
        raise HTTPException(status_code=400, detail="Activity is not active")
    if activity.loom_id is not None:
        raise HTTPException(status_code=400, detail="Activity already has a loom assigned")

    loom = await db.scalar(
        select(Loom).where(
            Loom.id == body.loom_id,
            Loom.owner_id == current_user.id,
            Loom.deleted_at.is_(None),
        )
    )
    if loom is None:
        raise HTTPException(status_code=404, detail="Loom not found")

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

    activity.loom_id = body.loom_id
    activity.loom_version_id = body.loom_version_id
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    return _to_detail(activity, project, loom)


@router.post("/{activity_id}/step", response_model=ActivityDetail)
async def step_activity(
    activity_id: uuid.UUID,
    body: StepRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    if body.direction not in ("advance", "reverse"):
        raise HTTPException(status_code=400, detail="direction must be 'advance' or 'reverse'")

    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "active":
        raise HTTPException(status_code=400, detail="Activity is not active")

    from_pick = activity.current_pick

    if body.direction == "advance":
        if activity.current_pick > activity.total_picks:
            raise HTTPException(status_code=400, detail="Already at last pick")
        activity.current_pick += 1
    else:
        if activity.current_pick <= 1:
            raise HTTPException(status_code=400, detail="Already at first pick")
        activity.current_pick -= 1

    step = ActivityStep(
        activity_id=activity.id,
        event_type=body.direction,
        from_pick=from_pick,
        to_pick=activity.current_pick,
    )
    db.add(step)
    await db.commit()
    await db.refresh(activity)

    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/jump", response_model=ActivityDetail)
async def jump_activity(
    activity_id: uuid.UUID,
    body: JumpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "active":
        raise HTTPException(status_code=400, detail="Activity is not active")
    activity.current_pick = max(1, min(body.pick, activity.total_picks + 1))
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/complete", response_model=ActivityDetail)
async def complete_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "active":
        raise HTTPException(status_code=400, detail="Activity is not active")
    activity.status = "completed"
    activity.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/abandon", response_model=ActivityDetail)
async def abandon_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "active":
        raise HTTPException(status_code=400, detail="Activity is not active")
    activity.status = "abandoned"
    activity.abandoned_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/restart", response_model=ActivityDetail)
async def restart_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    activity = await _get_owned_activity(activity_id, current_user, db)
    if activity.status != "abandoned":
        raise HTTPException(status_code=400, detail="Only abandoned activities can be restarted")
    if activity.loom_id:
        await _check_loom_conflict(activity.loom_id, activity.id, current_user.id, db)
    activity.status = "active"
    await db.commit()
    await db.refresh(activity)
    project = await db.get(Project, activity.project_id)
    loom = await db.get(Loom, activity.loom_id) if activity.loom_id else None
    return _to_detail(activity, project, loom)  # type: ignore[arg-type]


@router.post("/{activity_id}/clone", response_model=ActivityDetail, status_code=201)
async def clone_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityDetail:
    source = await _get_owned_activity(activity_id, current_user, db)
    if source.loom_id:
        await _check_loom_conflict(source.loom_id, None, current_user.id, db)
    clone = Activity(
        owner_id=current_user.id,
        project_id=source.project_id,
        loom_id=source.loom_id,
        loom_version_id=source.loom_version_id,
        name=source.name,
        activity_type=source.activity_type,
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
    project = await db.get(Project, clone.project_id)
    loom = await db.get(Loom, clone.loom_id) if clone.loom_id else None
    return _to_detail(clone, project, loom)  # type: ignore[arg-type]


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    activity = await _get_owned_activity(activity_id, current_user, db)
    activity.soft_delete()
    await db.commit()


@router.get("/{activity_id}/picks", response_model=PicksResponse)
async def get_picks(
    activity_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PicksResponse:
    activity = await _get_owned_activity(activity_id, current_user, db)
    project = await db.get(Project, activity.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    wif_bytes = storage.read_file(project.wif_path)
    try:
        pick_data = wif_parser.parse_picks(wif_bytes, activity.activity_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pick_rows = [
        PickRow(pick=i + 1, active=row, color=pick_data.weft_colors[i]) for i, row in enumerate(pick_data.picks)
    ]
    return PicksResponse(
        activity_type=pick_data.activity_type,
        total_picks=pick_data.total_picks,
        picks=pick_rows,
        has_weft_colors=any(p.color is not None for p in pick_rows),
    )
