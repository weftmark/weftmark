import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db
from app.models.project import Project
from app.models.user import User
from app.services import rendering, storage, wif_linter

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
    warp_threads: int | None
    weft_threads: int | None
    has_threading: bool
    has_tieup: bool
    has_treadling: bool
    has_liftplan: bool
    has_color_palette: bool
    lint_warnings: list[str]
    lint_errors: list[str]
    has_preview: bool
    is_shared: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_project(cls, p: Project) -> "ProjectSummary":
        data = {c.key: getattr(p, c.key) for c in p.__table__.columns}
        data["has_preview"] = storage.preview_exists(p.preview_path)
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
            project.lint_warnings = list(project.lint_warnings) + [
                f"Preview rendering failed: {exc}"
            ]

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
# Helpers
# ---------------------------------------------------------------------------

async def _get_owned_project(
    project_id: uuid.UUID, user: User, db: AsyncSession
) -> Project:
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
