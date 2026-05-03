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
from app.models.project import Project
from app.models.user import User
from app.services import rendering, storage, wif_linter, wif_modifier, wif_parser

router = APIRouter(prefix="/api/projects", tags=["projects"])
settings = get_settings()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
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
    def from_project(cls, p: Project) -> "ProjectSummary":
        data = {c.key: getattr(p, c.key) for c in p.__table__.columns}
        data["has_preview"] = storage.preview_exists(p.preview_path)
        data["has_modified_file"] = bool(p.wif_modified_path and storage.file_exists(p.wif_modified_path))
        return cls(**data)


class ProjectDetail(ProjectSummary):
    wif_source_software: str | None
    wif_source_version: str | None


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("", response_model=ProjectSummary, status_code=201)
async def create_project(
    name: Annotated[str, Form()],
    wif_file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectSummary:
    if not wif_file.filename or not wif_file.filename.lower().endswith(".wif"):
        raise HTTPException(status_code=400, detail="File must have a .wif extension")

    wif_bytes = await wif_file.read()
    if len(wif_bytes) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")

    lint = wif_linter.lint(wif_bytes)

    project = Project(
        owner_id=current_user.id,
        name=name,
        description=description,
        wif_filename=wif_file.filename,
        wif_path="",  # set after we have the project id
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
    db.add(project)
    await db.flush()  # get project.id without committing

    project.wif_path = storage.save_wif(project.id, wif_file.filename, wif_bytes)

    # Render preview if parseable
    if lint.is_parseable and not lint.errors:
        try:
            draft = rendering.load_draft(wif_bytes)
            png = rendering.render_full_draft(draft)
            project.preview_path = storage.save_preview(project.id, png)
        except Exception as exc:
            project.lint_warnings = list(project.lint_warnings) + [f"Preview rendering failed: {exc}"]

    await db.commit()
    await db.refresh(project)
    return ProjectSummary.from_project(project)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    result = await db.scalars(
        select(Project)
        .where(Project.owner_id == current_user.id, Project.deleted_at.is_(None))
        .order_by(Project.created_at.desc())
    )
    return [ProjectSummary.from_project(p) for p in result.all()]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)
    data = {c.key: getattr(project, c.key) for c in project.__table__.columns}
    data["has_preview"] = storage.preview_exists(project.preview_path)
    return ProjectDetail(**data)


# ---------------------------------------------------------------------------
# Preview image
# ---------------------------------------------------------------------------


@router.get("/{project_id}/preview")
async def get_preview(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(project_id, current_user, db)
    if not storage.preview_exists(project.preview_path):
        raise HTTPException(status_code=404, detail="Preview not available")
    png = storage.read_preview(project.preview_path)  # type: ignore[arg-type]
    return Response(content=png, media_type="image/png")


# ---------------------------------------------------------------------------
# Drawdown-only image
# ---------------------------------------------------------------------------


@router.get("/{project_id}/drawdown")
async def get_drawdown(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(project_id, current_user, db)
    if not project.wif_path:
        raise HTTPException(status_code=404, detail="No WIF file for this project")

    if not storage.file_exists(project.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not found in storage")

    wif_bytes = storage.read_file(project.wif_path)
    try:
        draft = rendering.load_draft(wif_bytes)
        png, total_rows = rendering.render_drawdown_only(draft)
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
            "ETag": f'"{project_id}"',
        },
    )


# ---------------------------------------------------------------------------
# WIF download
# ---------------------------------------------------------------------------


@router.get("/{project_id}/wif")
async def download_wif(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(project_id, current_user, db)
    if not project.wif_path or not storage.file_exists(project.wif_path):
        raise HTTPException(status_code=404, detail="WIF file not available for this project")
    wif_bytes = storage.read_file(project.wif_path)
    filename = project.wif_filename or "project.wif"
    return Response(
        content=wif_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# WIF with generated lift plan download
# ---------------------------------------------------------------------------


@router.get("/{project_id}/wif-modified")
async def download_wif_modified(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    project = await _get_owned_project(project_id, current_user, db)
    if not project.wif_modified_path or not storage.file_exists(project.wif_modified_path):
        raise HTTPException(status_code=404, detail="No modified WIF file for this project")
    wif_bytes = storage.read_file(project.wif_modified_path)
    base = (project.wif_filename or "project.wif").rsplit(".", 1)[0]
    filename = f"{base}-modified.wif"
    return Response(
        content=wif_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    project = await _get_owned_project(project_id, current_user, db)
    project.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Generate lift plan
# ---------------------------------------------------------------------------


@router.post("/{project_id}/generate-liftplan", response_model=ProjectDetail)
async def generate_liftplan(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await _get_owned_project(project_id, current_user, db)

    if not project.has_treadling:
        raise HTTPException(status_code=400, detail="WIF file has no [TREADLING] section — cannot compute lift plan")
    if not project.has_tieup:
        raise HTTPException(status_code=400, detail="WIF file has no [TIEUP] section — cannot compute lift plan")

    # Read from modified file if one exists (to chain onto prior modifications)
    has_mod = project.wif_modified_path and storage.file_exists(project.wif_modified_path)
    source_path = project.wif_modified_path if has_mod else project.wif_path
    wif_bytes = storage.read_file(source_path)
    try:
        updated_bytes = wif_parser.compute_liftplan(wif_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    modified_filename = project.wif_filename.rsplit(".", 1)[0] + "-modified.wif"
    project.wif_modified_path = storage.save_wif(project.id, modified_filename, updated_bytes)
    project.has_liftplan = True
    project.liftplan_generated = True

    await db.commit()
    await db.refresh(project)
    data = {c.key: getattr(project, c.key) for c in project.__table__.columns}
    data["has_preview"] = storage.preview_exists(project.preview_path)
    return ProjectDetail(**data)


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


@router.post("/{project_id}/override-metadata", response_model=ProjectDetail)
async def override_metadata(
    project_id: uuid.UUID,
    body: OverrideMetadataRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    if body.field not in _OVERRIDE_FIELDS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported field '{body.field}'. Allowed: {list(_OVERRIDE_FIELDS)}"
        )
    if body.value < 1:
        raise HTTPException(status_code=400, detail="Value must be >= 1")

    project = await _get_owned_project(project_id, current_user, db)

    # Read from modified file if one already exists, otherwise original
    source_path = (
        project.wif_modified_path
        if project.wif_modified_path and storage.file_exists(project.wif_modified_path)
        else project.wif_path
    )
    wif_bytes = storage.read_file(source_path)

    wif_key = _OVERRIDE_FIELDS[body.field]
    try:
        updated_bytes = wif_modifier.set_weaving_int(wif_bytes, wif_key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    modified_filename = project.wif_filename.rsplit(".", 1)[0] + "-modified.wif"
    project.wif_modified_path = storage.save_wif(project.id, modified_filename, updated_bytes)

    # Record the override (original value preserved for display)
    original_value = getattr(project, body.field)
    overrides = dict(project.metadata_overrides or {})
    overrides[body.field] = {"original": original_value, "override": body.value}
    project.metadata_overrides = overrides

    # Update the live metadata value on the project
    setattr(project, body.field, body.value)

    await db.commit()
    await db.refresh(project)
    data = {c.key: getattr(project, c.key) for c in project.__table__.columns}
    data["has_preview"] = storage.preview_exists(project.preview_path)
    data["has_modified_file"] = bool(project.wif_modified_path and storage.file_exists(project.wif_modified_path))
    return ProjectDetail(**data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_project(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,
            Project.deleted_at.is_(None),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
