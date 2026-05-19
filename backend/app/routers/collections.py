import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user, get_db
from app.models.collection import Collection, CollectionDraft, CollectionProject
from app.models.draft import Draft
from app.models.project import Project
from app.models.user import User

router = APIRouter(prefix="/api/collections", tags=["collections"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CollectionSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    tags: list[str]
    draft_count: int
    project_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DraftMember(BaseModel):
    id: uuid.UUID
    name: str
    wif_filename: str
    has_preview: bool
    num_shafts: int | None
    num_treadles: int | None
    added_at: datetime

    model_config = {"from_attributes": True}


class ProjectMember(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    added_at: datetime

    model_config = {"from_attributes": True}


class CollectionDetail(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    tags: list[str]
    drafts: list[DraftMember]
    projects: list[ProjectMember]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CreateCollectionRequest(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] = []


class UpdateCollectionRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class AddDraftRequest(BaseModel):
    draft_id: uuid.UUID


class AddProjectRequest(BaseModel):
    project_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_collection(collection_id: uuid.UUID, user: User, db: AsyncSession) -> Collection:
    c = await db.scalar(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user.id,
            Collection.deleted_at.is_(None),
        )
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return c


def _summary(c: Collection) -> CollectionSummary:
    return CollectionSummary(
        id=c.id,
        name=c.name,
        description=c.description,
        tags=c.tags or [],
        draft_count=len(c.draft_links),
        project_count=len(c.project_links),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=CollectionSummary)
async def create_collection(
    body: CreateCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionSummary:
    c = Collection(owner_id=current_user.id, name=body.name, description=body.description, tags=body.tags)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return CollectionSummary(
        id=c.id,
        name=c.name,
        description=c.description,
        tags=c.tags or [],
        draft_count=0,
        project_count=0,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("", response_model=list[CollectionSummary])
async def list_collections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CollectionSummary]:
    result = await db.scalars(
        select(Collection)
        .where(Collection.owner_id == current_user.id, Collection.deleted_at.is_(None))
        .options(selectinload(Collection.draft_links), selectinload(Collection.project_links))
        .order_by(Collection.created_at.desc())
    )
    return [_summary(c) for c in result.all()]


@router.get("/{collection_id}", response_model=CollectionDetail)
async def get_collection(
    collection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionDetail:
    c = await db.scalar(
        select(Collection)
        .where(
            Collection.id == collection_id,
            Collection.owner_id == current_user.id,
            Collection.deleted_at.is_(None),
        )
        .options(
            selectinload(Collection.draft_links),
            selectinload(Collection.project_links),
        )
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    draft_ids = {link.draft_id: link.added_at for link in c.draft_links}
    project_ids = {link.project_id: link.added_at for link in c.project_links}

    drafts: list[DraftMember] = []
    if draft_ids:
        draft_rows = (await db.scalars(select(Draft).where(Draft.id.in_(draft_ids), Draft.deleted_at.is_(None)))).all()
        for d in draft_rows:
            from app.services import storage

            drafts.append(
                DraftMember(
                    id=d.id,
                    name=d.name,
                    wif_filename=d.wif_filename,
                    has_preview=storage.preview_exists(d.preview_path),
                    num_shafts=d.num_shafts,
                    num_treadles=d.num_treadles,
                    added_at=draft_ids[d.id],
                )
            )

    projects: list[ProjectMember] = []
    if project_ids:
        proj_rows = (
            await db.scalars(select(Project).where(Project.id.in_(project_ids), Project.deleted_at.is_(None)))
        ).all()
        for p in proj_rows:
            projects.append(ProjectMember(id=p.id, name=p.name, status=p.status, added_at=project_ids[p.id]))

    return CollectionDetail(
        id=c.id,
        name=c.name,
        description=c.description,
        tags=c.tags or [],
        drafts=drafts,
        projects=projects,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.patch("/{collection_id}", response_model=CollectionSummary)
async def update_collection(
    collection_id: uuid.UUID,
    body: UpdateCollectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CollectionSummary:
    c = await db.scalar(
        select(Collection).where(
            Collection.id == collection_id, Collection.owner_id == current_user.id, Collection.deleted_at.is_(None)
        )
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if body.name is not None:
        c.name = body.name
    if body.description is not None:
        c.description = body.description
    if body.tags is not None:
        c.tags = body.tags
    await db.commit()
    # Re-query with eager load so _summary can read counts without lazy IO
    c = await db.scalar(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(selectinload(Collection.draft_links), selectinload(Collection.project_links))
    )
    return _summary(c)  # type: ignore[arg-type]


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    c = await _get_owned_collection(collection_id, current_user, db)
    c.soft_delete()
    await db.commit()


# ---------------------------------------------------------------------------
# Draft membership
# ---------------------------------------------------------------------------


@router.post("/{collection_id}/drafts", status_code=204)
async def add_draft(
    collection_id: uuid.UUID,
    body: AddDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    c = await _get_owned_collection(collection_id, current_user, db)

    draft = await db.scalar(
        select(Draft).where(Draft.id == body.draft_id, Draft.owner_id == current_user.id, Draft.deleted_at.is_(None))
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    existing = await db.scalar(
        select(CollectionDraft).where(CollectionDraft.collection_id == c.id, CollectionDraft.draft_id == body.draft_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Draft already in collection")

    db.add(CollectionDraft(collection_id=c.id, draft_id=body.draft_id, added_at=datetime.now(timezone.utc)))
    await db.commit()


@router.delete("/{collection_id}/drafts/{draft_id}", status_code=204)
async def remove_draft(
    collection_id: uuid.UUID,
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_owned_collection(collection_id, current_user, db)

    link = await db.scalar(
        select(CollectionDraft).where(
            CollectionDraft.collection_id == collection_id, CollectionDraft.draft_id == draft_id
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Draft not in collection")

    await db.delete(link)
    await db.commit()


# ---------------------------------------------------------------------------
# Project membership
# ---------------------------------------------------------------------------


@router.post("/{collection_id}/projects", status_code=204)
async def add_project(
    collection_id: uuid.UUID,
    body: AddProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    c = await _get_owned_collection(collection_id, current_user, db)

    project = await db.scalar(
        select(Project).where(
            Project.id == body.project_id, Project.owner_id == current_user.id, Project.deleted_at.is_(None)
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = await db.scalar(
        select(CollectionProject).where(
            CollectionProject.collection_id == c.id, CollectionProject.project_id == body.project_id
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Project already in collection")

    db.add(CollectionProject(collection_id=c.id, project_id=body.project_id, added_at=datetime.now(timezone.utc)))
    await db.commit()


@router.delete("/{collection_id}/projects/{project_id}", status_code=204)
async def remove_project(
    collection_id: uuid.UUID,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await _get_owned_collection(collection_id, current_user, db)

    link = await db.scalar(
        select(CollectionProject).where(
            CollectionProject.collection_id == collection_id, CollectionProject.project_id == project_id
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Project not in collection")

    await db.delete(link)
    await db.commit()
