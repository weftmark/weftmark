import asyncio
import importlib.metadata
import logging
import platform
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
import psutil
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.deps import get_db, require_admin, require_superuser
from app.models.audit_log import AuditLog
from app.models.draft import Draft
from app.models.eula_version import EulaVersion
from app.models.invite import Invite
from app.models.loom import Loom, LoomVersion, LoomVersionPhoto
from app.models.pending_signup import PendingSignup
from app.models.project import Project, ProjectPhoto
from app.models.user import User
from app.models.yarn import Yarn
from app.services.audit import write_audit_log
from app.services.clerk import ban_clerk_user, get_clerk_user, list_clerk_users, set_user_metadata, unban_clerk_user
from app.services.email import (
    send_account_approved_email,
    send_account_denied_email,
    send_approval_confirmation_to_admins,
    send_test_email,
)
from app.version import VERSION

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdminUserCounts(BaseModel):
    drafts: int
    projects_active: int
    projects_completed: int
    looms: int
    storage_bytes: int


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    is_superuser: bool
    is_active: bool
    clerk_banned: bool
    created_at: datetime
    last_active_at: datetime | None
    approved_by_name: str | None
    approved_by_email: str | None
    deletion_state: str | None
    deletion_initiated_at: datetime | None
    clerk_errored: bool
    counts: AdminUserCounts

    model_config = {"from_attributes": False}


class AdminUserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None
    is_superuser: bool | None = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    active_7d: int
    active_30d: int
    active_90d: int
    total_drafts: int
    total_projects: int
    total_looms: int
    total_yarn: int
    pending_invites: int
    total_storage_bytes: int


class AdminHealthResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: int
    memory_total_mb: int
    db_ping_ms: float
    uptime_seconds: int
    started_at: str


class AdminVersionsResponse(BaseModel):
    app: str
    python: str
    redis_server: str
    celery: str
    worker: str | None
    postgres: str
    postgres_source: str
    backend_packages: dict[str, str]


class AdminDbInfoResponse(BaseModel):
    revision: str | None
    is_at_head: bool
    last_squash_at: str | None
    last_migrated_at: str | None


class ServicePermCheck(BaseModel):
    name: str
    status: Literal["ok", "error"]
    message: str


class ServiceCheckResult(BaseModel):
    service: str
    status: Literal["ok", "error"]
    message: str
    checks: list[ServicePermCheck] = []
    meta: dict[str, str] = {}


def _make_result(
    service: str,
    checks: list[ServicePermCheck],
    meta: dict[str, str] | None = None,
) -> ServiceCheckResult:
    failed = [c for c in checks if c.status == "error"]
    status: Literal["ok", "error"] = "error" if failed else "ok"
    if failed:
        message = f"{len(failed)}/{len(checks)} check{'s' if len(failed) > 1 else ''} failed"
    else:
        message = f"{len(checks)}/{len(checks)} checks passed"
    return ServiceCheckResult(service=service, status=status, message=message, checks=checks, meta=meta or {})


def _pg_conn_meta() -> dict[str, str]:
    from urllib.parse import urlparse

    settings = get_settings()
    if settings.postgres_dsn:
        parsed = urlparse(settings.postgres_dsn)
        host = parsed.hostname or ""
        db = (parsed.path or "").lstrip("/")
        user = parsed.username or ""
        port = str(parsed.port) if parsed.port else "5432"
    else:
        host = settings.postgres_host
        db = settings.postgres_db
        user = settings.postgres_user
        port = str(settings.postgres_port)
    if "-pooler" in host:
        mode = "pooled (PgBouncer)"
    elif host in ("db", "localhost", "127.0.0.1"):
        mode = "local"
    else:
        mode = "direct"
    return {"host": host, "port": port, "database": db, "user": user, "mode": mode}


# ---------------------------------------------------------------------------
# Service-check probes
# ---------------------------------------------------------------------------


async def _probe_postgres(db: AsyncSession) -> ServiceCheckResult:
    checks: list[ServicePermCheck] = []
    meta = _pg_conn_meta()

    # 1. Connectivity
    try:
        t0 = time.monotonic()
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=3.0)
        ms = round((time.monotonic() - t0) * 1000, 1)
        checks.append(ServicePermCheck(name="connect", status="ok", message=f"SELECT 1 → {ms} ms"))
    except asyncio.TimeoutError:
        checks.append(ServicePermCheck(name="connect", status="error", message="Timed out after 3 s"))
        return _make_result("PostgreSQL", checks, meta=meta)
    except Exception as exc:
        checks.append(ServicePermCheck(name="connect", status="error", message=str(exc)[:120]))
        return _make_result("PostgreSQL", checks, meta=meta)

    # 2. Table privileges (SELECT / INSERT / UPDATE / DELETE on users table)
    try:
        row = (
            await db.execute(
                text(
                    "SELECT"
                    " has_table_privilege(current_user, 'users', 'SELECT') AS sel,"
                    " has_table_privilege(current_user, 'users', 'INSERT') AS ins,"
                    " has_table_privilege(current_user, 'users', 'UPDATE') AS upd,"
                    " has_table_privilege(current_user, 'users', 'DELETE') AS del_ok,"
                    " has_schema_privilege(current_user, 'public', 'USAGE') AS schema_ok"
                )
            )
        ).one()
        for priv, col in [("SELECT", row.sel), ("INSERT", row.ins), ("UPDATE", row.upd), ("DELETE", row.del_ok)]:
            checks.append(
                ServicePermCheck(
                    name=priv.lower(),
                    status="ok" if col else "error",
                    message="granted" if col else "not granted on users table",
                )
            )
        checks.append(
            ServicePermCheck(
                name="schema_usage",
                status="ok" if row.schema_ok else "error",
                message="USAGE on public granted" if row.schema_ok else "USAGE on public not granted",
            )
        )
    except Exception as exc:
        checks.append(ServicePermCheck(name="privileges", status="error", message=str(exc)[:120]))

    return _make_result("PostgreSQL", checks, meta=meta)


def _s3_conn_meta(settings: "Settings") -> dict[str, str]:
    if settings.storage_backend != "s3":
        return {"backend": "local"}
    return {
        "backend": "s3",
        "bucket": settings.s3_bucket_name or "(not set)",
        "endpoint": settings.s3_endpoint_url or "AWS default",
        "region": settings.s3_region or "auto",
        "access_key_id": settings.s3_access_key_id or "(not set)",
    }


async def _probe_s3() -> ServiceCheckResult:
    settings = get_settings()
    checks: list[ServicePermCheck] = []
    meta = _s3_conn_meta(settings)

    if settings.storage_backend != "s3":
        checks.append(ServicePermCheck(name="storage_backend", status="ok", message="Local storage — S3 not in use"))
        return _make_result("S3", checks, meta=meta)

    if not settings.s3_bucket_name:
        checks.append(ServicePermCheck(name="config", status="error", message="S3_BUCKET_NAME not set"))
        return _make_result("S3", checks, meta=meta)

    def _run_checks() -> list[tuple[str, bool, str]]:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region or "auto",
        )
        bucket = settings.s3_bucket_name
        results: list[tuple[str, bool, str]] = []

        # bucket_accessible
        try:
            client.head_bucket(Bucket=bucket)
            results.append(("bucket_accessible", True, f"Bucket '{bucket}' found"))
        except Exception as e:
            results.append(("bucket_accessible", False, str(e)[:100]))
            return results  # further checks will also fail

        # list_objects
        try:
            client.list_objects_v2(Bucket=bucket, MaxKeys=1)
            results.append(("list_objects", True, "ListObjectsV2 permitted"))
        except Exception as e:
            results.append(("list_objects", False, str(e)[:100]))

        # write + delete (combined — put then clean up)
        test_key = "_health_check"
        try:
            client.put_object(Bucket=bucket, Key=test_key, Body=b"ok")
            try:
                client.delete_object(Bucket=bucket, Key=test_key)
                results.append(("write_delete", True, "PutObject + DeleteObject permitted"))
            except Exception as e:
                results.append(("write_delete", False, f"Put OK but delete failed: {e!s:.80}"))
        except Exception as e:
            results.append(("write_delete", False, str(e)[:100]))

        return results

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_run_checks), timeout=10.0)
        for name, ok, msg in raw:
            checks.append(ServicePermCheck(name=name, status="ok" if ok else "error", message=msg))
    except asyncio.TimeoutError:
        checks.append(ServicePermCheck(name="connect", status="error", message="Timed out after 10 s"))

    return _make_result("S3", checks, meta=meta)


def _clerk_conn_meta(settings: "Settings") -> dict[str, str]:
    pk = settings.clerk_publishable_key
    return {
        "publishable_key": pk or "(not set)",
        "environment": "live" if pk and pk.startswith("pk_live_") else "test",
    }


async def _probe_clerk() -> ServiceCheckResult:
    settings = get_settings()
    checks: list[ServicePermCheck] = []
    meta = _clerk_conn_meta(settings)

    # Config: secret key
    sk = settings.clerk_secret_key
    sk_ok = bool(sk and sk.startswith("sk_"))
    if sk_ok:
        sk_pfx = "sk_live_" if sk.startswith("sk_live_") else "sk_test_"
        sk_peek = sk[len(sk_pfx) : len(sk_pfx) + 6]
        sk_msg = f"Set ({sk_pfx}{sk_peek}…)"
    else:
        sk_msg = "Missing or unexpected format"
    checks.append(ServicePermCheck(name="secret_key", status="ok" if sk_ok else "error", message=sk_msg))

    # Config: publishable key
    pk_ok = bool(settings.clerk_publishable_key and settings.clerk_publishable_key.startswith("pk_"))
    checks.append(
        ServicePermCheck(
            name="publishable_key",
            status="ok" if pk_ok else "error",
            message="Set (pk_…)" if pk_ok else "Missing or unexpected format",
        )
    )

    # Config: webhook secret
    wh_ok = bool(settings.clerk_webhook_secret and settings.clerk_webhook_secret.startswith("whsec_"))
    checks.append(
        ServicePermCheck(
            name="webhook_secret",
            status="ok" if wh_ok else "error",
            message="Set (whsec_…)" if wh_ok else "Missing or unexpected format",
        )
    )

    # API connectivity + auth
    if not settings.clerk_secret_key:
        checks.append(ServicePermCheck(name="api_auth", status="error", message="Skipped — secret key missing"))
        return _make_result("Clerk", checks, meta=meta)

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                "https://api.clerk.com/v1/users?limit=1",
                headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            )
        if r.status_code == 200:
            checks.append(ServicePermCheck(name="api_auth", status="ok", message="GET /v1/users → 200"))
        else:
            checks.append(ServicePermCheck(name="api_auth", status="error", message=f"HTTP {r.status_code}"))
    except httpx.TimeoutException:
        checks.append(ServicePermCheck(name="api_auth", status="error", message="Timed out after 3 s"))
    except Exception as exc:
        checks.append(ServicePermCheck(name="api_auth", status="error", message=str(exc)[:120]))

    return _make_result("Clerk", checks, meta=meta)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    from sqlalchemy import or_

    users = list(
        (
            await db.scalars(
                select(User)
                .where(or_(User.deleted_at.is_(None), User.deletion_state.is_not(None)))
                .order_by(User.created_at.asc())
            )
        ).all()
    )
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Per-user draft counts
    draft_rows = (
        await db.execute(
            select(Draft.owner_id, func.count().label("cnt"))
            .where(Draft.owner_id.in_(user_ids), Draft.deleted_at.is_(None))
            .group_by(Draft.owner_id)
        )
    ).all()
    draft_counts = {row.owner_id: row.cnt for row in draft_rows}

    # Per-user project counts by status
    project_rows = (
        await db.execute(
            select(Project.owner_id, Project.status, func.count().label("cnt"))
            .where(Project.owner_id.in_(user_ids), Project.deleted_at.is_(None))
            .group_by(Project.owner_id, Project.status)
        )
    ).all()
    project_active: dict[uuid.UUID, int] = {}
    project_completed: dict[uuid.UUID, int] = {}
    for row in project_rows:
        if row.status == "active":
            project_active[row.owner_id] = row.cnt
        elif row.status == "completed":
            project_completed[row.owner_id] = row.cnt

    # Per-user loom counts
    loom_rows = (
        await db.execute(
            select(Loom.owner_id, func.count().label("cnt"))
            .where(Loom.owner_id.in_(user_ids), Loom.deleted_at.is_(None))
            .group_by(Loom.owner_id)
        )
    ).all()
    loom_counts = {row.owner_id: row.cnt for row in loom_rows}

    # Per-user storage: project photos
    project_storage_rows = (
        await db.execute(
            select(Project.owner_id, func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0).label("bytes"))
            .join(ProjectPhoto, ProjectPhoto.project_id == Project.id)
            .where(Project.owner_id.in_(user_ids))
            .group_by(Project.owner_id)
        )
    ).all()
    storage_bytes: dict[uuid.UUID, int] = {row.owner_id: int(row.bytes) for row in project_storage_rows}

    # Per-user storage: loom version photos
    loom_storage_rows = (
        await db.execute(
            select(Loom.owner_id, func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0).label("bytes"))
            .join(LoomVersion, LoomVersion.loom_id == Loom.id)
            .join(LoomVersionPhoto, LoomVersionPhoto.loom_version_id == LoomVersion.id)
            .where(Loom.owner_id.in_(user_ids))
            .group_by(Loom.owner_id)
        )
    ).all()
    for row in loom_storage_rows:
        storage_bytes[row.owner_id] = storage_bytes.get(row.owner_id, 0) + int(row.bytes)

    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_admin=u.is_admin,
            is_active=u.is_active,
            clerk_banned=u.clerk_banned,
            created_at=u.created_at,
            last_active_at=u.last_active_at,
            approved_by_name=u.approved_by_name,
            approved_by_email=u.approved_by_email,
            is_superuser=u.is_superuser,
            deletion_state=u.deletion_state,
            deletion_initiated_at=u.deletion_initiated_at,
            clerk_errored=u.clerk_errored,
            counts=AdminUserCounts(
                drafts=draft_counts.get(u.id, 0),
                projects_active=project_active.get(u.id, 0),
                projects_completed=project_completed.get(u.id, 0),
                looms=loom_counts.get(u.id, 0),
                storage_bytes=storage_bytes.get(u.id, 0),
            ),
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def patch_user(
    user_id: uuid.UUID,
    body: AdminUserPatch,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")

    if body.is_admin is not None or body.is_superuser is not None:
        if not admin.is_superuser:
            raise HTTPException(status_code=403, detail="Superuser required to change admin or superuser roles")
        if body.is_admin is False and user.is_superuser:
            raise HTTPException(status_code=400, detail="Cannot remove admin from a superuser")

    if body.is_active is False and user.is_admin:
        raise HTTPException(status_code=422, detail="Remove admin rights before deactivating this user")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.is_superuser is not None:
        user.is_superuser = body.is_superuser

    changed = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    await write_audit_log(db, event_type="user.role_changed", actor=admin, target=user, details=changed)
    await db.commit()
    await db.refresh(user)

    if (body.is_admin is not None or body.is_superuser is not None) and user.clerk_user_id:
        await set_user_metadata(user.clerk_user_id, {"is_admin": user.is_admin, "is_superuser": user.is_superuser})

    # Re-fetch counts for the patched user
    drafts = (
        await db.scalar(
            select(func.count()).select_from(Draft).where(Draft.owner_id == user.id, Draft.deleted_at.is_(None))
        )
        or 0
    )
    proj_active = (
        await db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.owner_id == user.id, Project.status == "active", Project.deleted_at.is_(None))
        )
        or 0
    )
    proj_completed = (
        await db.scalar(
            select(func.count())
            .select_from(Project)
            .where(Project.owner_id == user.id, Project.status == "completed", Project.deleted_at.is_(None))
        )
        or 0
    )
    looms = (
        await db.scalar(
            select(func.count()).select_from(Loom).where(Loom.owner_id == user.id, Loom.deleted_at.is_(None))
        )
        or 0
    )
    project_storage = (
        await db.scalar(
            select(func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0))
            .join(Project, ProjectPhoto.project_id == Project.id)
            .where(Project.owner_id == user.id)
        )
        or 0
    )
    loom_storage = (
        await db.scalar(
            select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))
            .join(LoomVersion, LoomVersionPhoto.loom_version_id == LoomVersion.id)
            .join(Loom, LoomVersion.loom_id == Loom.id)
            .where(Loom.owner_id == user.id)
        )
        or 0
    )

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        deletion_state=user.deletion_state,
        deletion_initiated_at=user.deletion_initiated_at,
        clerk_errored=user.clerk_errored,
        counts=AdminUserCounts(
            drafts=drafts,
            projects_active=proj_active,
            projects_completed=proj_completed,
            looms=looms,
            storage_bytes=int(project_storage) + int(loom_storage),
        ),
    )


# ---------------------------------------------------------------------------
# Ban / unban
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/ban", status_code=200)
async def ban_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban your own account")
    if not user.clerk_user_id:
        raise HTTPException(status_code=400, detail="User has no Clerk account")
    if user.is_admin:
        raise HTTPException(status_code=422, detail="Remove admin rights before banning this user")

    await ban_clerk_user(user.clerk_user_id)
    await set_user_metadata(user.clerk_user_id, {"status": "banned"})
    user.clerk_banned = True
    user.is_active = False
    await write_audit_log(db, event_type="user.banned", actor=admin, target=user)
    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        deletion_state=user.deletion_state,
        deletion_initiated_at=user.deletion_initiated_at,
        clerk_errored=user.clerk_errored,
        counts=AdminUserCounts(drafts=0, projects_active=0, projects_completed=0, looms=0, storage_bytes=0),
    )


@router.post("/users/{user_id}/unban", status_code=200)
async def unban_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.clerk_user_id:
        raise HTTPException(status_code=400, detail="User has no Clerk account")

    await unban_clerk_user(user.clerk_user_id)
    await set_user_metadata(user.clerk_user_id, {"status": "active"})
    user.clerk_banned = False
    user.is_active = True
    await write_audit_log(db, event_type="user.unbanned", actor=admin, target=user)
    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        deletion_state=user.deletion_state,
        deletion_initiated_at=user.deletion_initiated_at,
        clerk_errored=user.clerk_errored,
        counts=AdminUserCounts(drafts=0, projects_active=0, projects_completed=0, looms=0, storage_bytes=0),
    )


# ---------------------------------------------------------------------------
# Delete user
# ---------------------------------------------------------------------------


class DeleteUserRequest(BaseModel):
    confirm: str


@router.post("/users/{user_id}/delete", status_code=202)
async def delete_user(
    user_id: uuid.UUID,
    body: DeleteUserRequest,
    requesting_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.confirm != "DELETE USER":
        raise HTTPException(status_code=422, detail='confirm must be exactly "DELETE USER"')

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == requesting_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account via admin panel")
    if user.deletion_state is not None:
        raise HTTPException(status_code=409, detail=f"Deletion already in state: {user.deletion_state}")

    from app.services.deletion import initiate_user_deletion

    await write_audit_log(
        db,
        event_type="user.deleted",
        actor=requesting_user,
        target_user_id=user.id,
        target_email=user.email,
    )
    await initiate_user_deletion(db, user)
    log.info("admin_delete_initiated user_id=%s by=%s", user_id, requesting_user.email)

    return {"status": "pending", "user_id": str(user_id)}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    now = datetime.now(timezone.utc)

    async def count(stmt):  # type: ignore[no-untyped-def]
        return await db.scalar(stmt) or 0

    total_users = await count(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
    active_users = await count(
        select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    )
    active_7d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=7))
    )
    active_30d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=30))
    )
    active_90d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=90))
    )
    total_drafts = await count(select(func.count()).select_from(Draft).where(Draft.deleted_at.is_(None)))
    total_projects = await count(select(func.count()).select_from(Project).where(Project.deleted_at.is_(None)))
    total_looms = await count(select(func.count()).select_from(Loom).where(Loom.deleted_at.is_(None)))
    total_yarn = await count(select(func.count()).select_from(Yarn).where(Yarn.deleted_at.is_(None)))
    pending_invites = await count(
        select(func.count())
        .select_from(Invite)
        .where(Invite.accepted_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > now)
    )
    project_storage = await db.scalar(select(func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0))) or 0
    loom_storage = await db.scalar(select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))) or 0

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        active_7d=active_7d,
        active_30d=active_30d,
        active_90d=active_90d,
        total_drafts=total_drafts,
        total_projects=total_projects,
        total_looms=total_looms,
        total_yarn=total_yarn,
        pending_invites=pending_invites,
        total_storage_bytes=int(project_storage) + int(loom_storage),
    )


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@router.get("/health", response_model=AdminHealthResponse)
async def get_health(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminHealthResponse:
    from app.main import start_time

    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    t0 = time.monotonic()
    await db.execute(text("SELECT 1"))
    db_ping_ms = round((time.monotonic() - t0) * 1000, 1)

    uptime_seconds = int((datetime.now(timezone.utc) - start_time).total_seconds())

    return AdminHealthResponse(
        cpu_percent=cpu,
        memory_percent=round(mem.percent, 1),
        memory_used_mb=mem.used // (1024 * 1024),
        memory_total_mb=mem.total // (1024 * 1024),
        db_ping_ms=db_ping_ms,
        uptime_seconds=uptime_seconds,
        started_at=start_time.isoformat(),
    )


def _smtp_conn_meta(settings: "Settings") -> dict[str, str]:
    return {
        "host": settings.smtp_host or "(not set)",
        "port": str(settings.smtp_port),
        "user": settings.smtp_user or "(not set)",
        "from": settings.smtp_from_email or "(not set)",
        "from_name": settings.smtp_from_name or "(not set)",
    }


async def _probe_smtp() -> ServiceCheckResult:
    import aiosmtplib

    settings = get_settings()
    checks: list[ServicePermCheck] = []
    meta = _smtp_conn_meta(settings)

    if not settings.smtp_host:
        checks.append(
            ServicePermCheck(name="config", status="error", message="not configured — emails will not be sent")
        )
        return _make_result("SMTP", checks, meta=meta)

    missing = [
        k
        for k, v in {
            "smtp_user": settings.smtp_user,
            "smtp_password": settings.smtp_password,
            "smtp_from_email": settings.smtp_from_email,
        }.items()
        if not v
    ]
    if missing:
        checks.append(ServicePermCheck(name="config", status="error", message=f"Missing: {', '.join(missing)}"))
        return _make_result("SMTP", checks, meta=meta)
    checks.append(
        ServicePermCheck(name="config", status="ok", message=f"{settings.smtp_host}:{settings.smtp_port} configured")
    )

    # start_tls=True mirrors aiosmtplib.send() — connect() handles STARTTLS automatically
    smtp = aiosmtplib.SMTP(hostname=settings.smtp_host, port=settings.smtp_port, start_tls=True, timeout=5)

    try:
        await asyncio.wait_for(smtp.connect(), timeout=5.0)
        checks.append(
            ServicePermCheck(
                name="connect", status="ok", message=f"TCP connected to {settings.smtp_host}:{settings.smtp_port}"
            )
        )
        checks.append(ServicePermCheck(name="starttls", status="ok", message="STARTTLS negotiated"))
    except (asyncio.TimeoutError, Exception) as exc:
        msg = "Timed out after 5 s" if isinstance(exc, asyncio.TimeoutError) else str(exc)[:120]
        checks.append(ServicePermCheck(name="connect", status="error", message=msg))
        return _make_result("SMTP", checks, meta=meta)

    try:
        await asyncio.wait_for(smtp.login(settings.smtp_user, settings.smtp_password), timeout=5.0)
        checks.append(ServicePermCheck(name="auth", status="ok", message=f"Authenticated as {settings.smtp_user}"))
    except (asyncio.TimeoutError, Exception) as exc:
        msg = "Timed out after 5 s" if isinstance(exc, asyncio.TimeoutError) else str(exc)[:120]
        checks.append(ServicePermCheck(name="auth", status="error", message=msg))
    finally:
        try:
            await smtp.quit()
        except Exception:
            pass

    return _make_result("SMTP", checks, meta=meta)


# ---------------------------------------------------------------------------
# Services connection check
# ---------------------------------------------------------------------------


def _probe_webhook_info() -> ServiceCheckResult:
    settings = get_settings()
    checks: list[ServicePermCheck] = []

    base = (settings.webhook_base_url or settings.api_url).rstrip("/")
    meta = {"url": base + "/auth/clerk/webhook"}

    if settings.clerk_webhook_secret and settings.clerk_webhook_secret.startswith("whsec_"):
        checks.append(ServicePermCheck(name="secret", status="ok", message="configured"))
    else:
        checks.append(
            ServicePermCheck(name="secret", status="error", message="CLERK_WEBHOOK_SECRET not configured or invalid")
        )

    if settings.cf_zero_trust_enabled:
        checks.append(
            ServicePermCheck(
                name="cf_access",
                status="ok",
                message="Enabled — requests pass through Cloudflare Zero Trust / Access",
            )
        )
        if settings.cf_access_client_id:
            checks.append(ServicePermCheck(name="cf_client_id", status="ok", message=settings.cf_access_client_id))
        else:
            checks.append(ServicePermCheck(name="cf_client_id", status="error", message="CF_ACCESS_CLIENT_ID not set"))
        if settings.cf_access_client_secret:
            s = settings.cf_access_client_secret
            obfuscated = s[:6] + "••••••" if len(s) > 6 else "••••••"
            checks.append(ServicePermCheck(name="cf_client_secret", status="ok", message=obfuscated))
        else:
            checks.append(
                ServicePermCheck(name="cf_client_secret", status="error", message="CF_ACCESS_CLIENT_SECRET not set")
            )
    else:
        checks.append(ServicePermCheck(name="cf_access", status="ok", message="Disabled"))

    return _make_result("Clerk Webhook", checks, meta=meta)


@router.get("/services", response_model=list[ServiceCheckResult])
async def check_services(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ServiceCheckResult]:
    db_result, s3_result, clerk_result, smtp_result = await asyncio.gather(
        _probe_postgres(db),
        _probe_s3(),
        _probe_clerk(),
        _probe_smtp(),
    )
    return [db_result, s3_result, clerk_result, smtp_result, _probe_webhook_info()]


# ---------------------------------------------------------------------------
# Webhook probe
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    actor_email: str | None
    event_type: str
    target_email: str | None
    details: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    pages: int


class WebhookProbeResponse(BaseModel):
    status: Literal["ok", "skipped", "error"]
    latency_ms: int | None = None
    message: str = ""


@router.post("/test-webhook", response_model=WebhookProbeResponse, status_code=200)
async def test_webhook(
    _: User = Depends(require_superuser),
) -> WebhookProbeResponse:
    from app.services.clerk_webhook_probe import run_webhook_probe

    result = await run_webhook_probe()
    return WebhookProbeResponse(status=result.status, latency_ms=result.latency_ms, message=result.message)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@router.get("/audit-log", response_model=AuditLogPage)
async def list_audit_log(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
    event_type: str | None = None,
    q: str | None = None,
) -> AuditLogPage:
    from sqlalchemy import or_

    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)

    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
        count_stmt = count_stmt.where(AuditLog.event_type == event_type)
    if q:
        like = f"%{q}%"
        filter_q = or_(AuditLog.actor_email.ilike(like), AuditLog.target_email.ilike(like))
        stmt = stmt.where(filter_q)
        count_stmt = count_stmt.where(filter_q)

    total = await db.scalar(count_stmt) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    rows = await db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size))
    items = [
        AuditLogEntry(
            id=r.id,
            actor_email=r.actor_email,
            event_type=r.event_type,
            target_email=r.target_email,
            details=r.details,
            created_at=r.created_at,
        )
        for r in rows.all()
    ]
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size, pages=pages)


# ---------------------------------------------------------------------------
# Test email
# ---------------------------------------------------------------------------


@router.post("/test-email", status_code=200)
async def send_test_email_endpoint(
    admin: User = Depends(require_admin),
) -> dict:
    await send_test_email(admin.email)
    return {"status": "sent", "to": admin.email}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Elevate admin to superuser
# ---------------------------------------------------------------------------


class ElevateContentSummary(BaseModel):
    projects: int
    looms: int
    drafts: int
    yarn: int


class ElevateRequest(BaseModel):
    confirm_delete_content: bool = False


@router.post("/users/{user_id}/elevate-to-superuser", status_code=200)
async def elevate_to_superuser(
    user_id: uuid.UUID,
    body: ElevateRequest,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_admin:
        raise HTTPException(status_code=400, detail="User must be an admin before being elevated to superuser")
    if user.is_superuser:
        raise HTTPException(status_code=400, detail="User is already a superuser")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot elevate yourself")

    projects = (
        await db.scalar(
            select(func.count()).select_from(Project).where(Project.owner_id == user_id, Project.deleted_at.is_(None))
        )
        or 0
    )
    looms = (
        await db.scalar(
            select(func.count()).select_from(Loom).where(Loom.owner_id == user_id, Loom.deleted_at.is_(None))
        )
        or 0
    )
    drafts = (
        await db.scalar(
            select(func.count()).select_from(Draft).where(Draft.owner_id == user_id, Draft.deleted_at.is_(None))
        )
        or 0
    )
    yarn = (
        await db.scalar(
            select(func.count()).select_from(Yarn).where(Yarn.owner_id == user_id, Yarn.deleted_at.is_(None))
        )
        or 0
    )

    has_content = any([projects, looms, drafts, yarn])

    if has_content and not body.confirm_delete_content:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "has_content",
                "summary": {"projects": projects, "looms": looms, "drafts": drafts, "yarn": yarn},
            },
        )

    if has_content:
        await db.execute(Project.__table__.delete().where(Project.owner_id == user_id))
        await db.execute(Loom.__table__.delete().where(Loom.owner_id == user_id))
        await db.execute(Draft.__table__.delete().where(Draft.owner_id == user_id))
        await db.execute(Yarn.__table__.delete().where(Yarn.owner_id == user_id))

    user.is_superuser = True
    await write_audit_log(
        db,
        event_type="user.elevated",
        actor=admin,
        target=user,
        details={"content_deleted": has_content},
    )
    await db.commit()
    if user.clerk_user_id:
        await set_user_metadata(user.clerk_user_id, {"is_superuser": True})

    return {"status": "elevated"}


# ---------------------------------------------------------------------------
# Pending signups
# ---------------------------------------------------------------------------


class PendingSignupResponse(BaseModel):
    id: uuid.UUID
    clerk_user_id: str
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/pending-signups", response_model=list[PendingSignupResponse])
async def list_pending_signups(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PendingSignup]:
    result = await db.scalars(select(PendingSignup).order_by(PendingSignup.created_at.desc()))
    return list(result.all())


@router.post("/pending-signups/{signup_id}/approve", response_model=None, status_code=201)
async def approve_pending_signup(
    signup_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")

    existing = await db.scalar(
        select(User).where(User.clerk_user_id == signup.clerk_user_id, User.deleted_at.is_(None))
    )
    if existing is not None:
        await db.delete(signup)
        await db.commit()
        return {"status": "already_exists"}

    # Attach to a pre-created User (from a prior invite) if one exists for this email.
    pre_created = await db.scalar(
        select(User).where(User.email == signup.email, User.clerk_user_id.is_(None), User.deleted_at.is_(None))
    )
    if pre_created is not None:
        pre_created.clerk_user_id = signup.clerk_user_id
        pre_created.display_name = signup.display_name
        pre_created.approved_by_name = admin.display_name
        pre_created.approved_by_email = admin.email
        user = pre_created
    else:
        user = User(
            email=signup.email,
            display_name=signup.display_name,
            clerk_user_id=signup.clerk_user_id,
            is_admin=False,
            approved_by_name=admin.display_name,
            approved_by_email=admin.email,
        )
        db.add(user)

    # Revoke any pending invites for this email so they clear from the invite list.
    pending_invites = await db.scalars(
        select(Invite).where(
            Invite.email == signup.email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    for invite in pending_invites:
        invite.revoked_at = now

    await db.delete(signup)
    await write_audit_log(
        db,
        event_type="signup.approved",
        actor=admin,
        target_email=signup.email,
    )
    await db.commit()
    await set_user_metadata(
        signup.clerk_user_id, {"status": "active", "is_admin": user.is_admin, "is_superuser": False}
    )

    admin_emails = list(await db.scalars(select(User.email).where(User.is_admin.is_(True), User.deleted_at.is_(None))))

    try:
        await send_account_approved_email(signup.email, signup.display_name)
    except Exception:
        log.exception("Failed to send account approved email to %s", signup.email)

    if admin_emails:
        try:
            await send_approval_confirmation_to_admins(
                admin_emails, signup.display_name, signup.email, admin.display_name
            )
        except Exception:
            log.exception("Failed to send approval confirmation to admins")

    return {"status": "created"}


@router.post("/pending-signups/{signup_id}/ban", status_code=204)
async def ban_pending_signup(
    signup_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    email, display_name, clerk_user_id = signup.email, signup.display_name, signup.clerk_user_id
    await write_audit_log(db, event_type="signup.banned", actor=admin, target_email=email)
    await db.delete(signup)
    await db.commit()
    await ban_clerk_user(clerk_user_id)
    await set_user_metadata(clerk_user_id, {"status": "banned"})
    try:
        await send_account_denied_email(email, display_name)
    except Exception:
        log.exception("Failed to send account denied email to %s", email)


@router.delete("/pending-signups/{signup_id}", status_code=204)
async def dismiss_pending_signup(
    signup_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    email, display_name, clerk_user_id = signup.email, signup.display_name, signup.clerk_user_id
    await write_audit_log(db, event_type="signup.dismissed", actor=admin, target_email=email)
    await db.delete(signup)
    await db.commit()
    await set_user_metadata(clerk_user_id, {"status": "denied"})
    try:
        await send_account_denied_email(email, display_name)
    except Exception:
        log.exception("Failed to send account denied email to %s", email)


# ---------------------------------------------------------------------------
# EULA management (superuser only)
# ---------------------------------------------------------------------------


class EulaCreateRequest(BaseModel):
    version: str
    body_html: str
    effective_date: datetime | None = None


class EulaVersionResponse(BaseModel):
    id: int
    version: str
    effective_date: datetime
    created_at: datetime


class EulaCurrentAdminResponse(BaseModel):
    id: int
    version: str
    body_html: str
    effective_date: datetime
    created_at: datetime


@router.get("/eula", response_model=EulaCurrentAdminResponse)
async def get_eula_admin(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> EulaCurrentAdminResponse:
    row = await db.scalar(
        select(EulaVersion).order_by(EulaVersion.effective_date.desc(), EulaVersion.id.desc()).limit(1)
    )
    if not row:
        raise HTTPException(status_code=404, detail="No EULA version found")
    return EulaCurrentAdminResponse(
        id=row.id,
        version=row.version,
        body_html=row.body_html,
        effective_date=row.effective_date,
        created_at=row.created_at,
    )


@router.post("/eula", response_model=EulaVersionResponse, status_code=201)
async def create_eula_version(
    body: EulaCreateRequest,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> EulaVersionResponse:
    existing = await db.scalar(select(EulaVersion).where(EulaVersion.version == body.version))
    if existing:
        raise HTTPException(status_code=409, detail=f"EULA version '{body.version}' already exists")

    effective = body.effective_date or datetime.now(timezone.utc)
    row = EulaVersion(version=body.version, body_html=body.body_html, effective_date=effective)
    db.add(row)
    await write_audit_log(db, event_type="eula.created", actor=admin, details={"version": body.version})
    await db.commit()
    await db.refresh(row)
    log.info("New EULA version created: %s (effective %s)", row.version, row.effective_date)
    return EulaVersionResponse(
        id=row.id,
        version=row.version,
        effective_date=row.effective_date,
        created_at=row.created_at,
    )


def _pkg(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _all_packages() -> dict[str, str]:
    """Return all packages listed in requirements.txt with their installed versions."""
    import re

    req_path = "/app/requirements.txt"
    try:
        with open(req_path) as f:
            lines = f.readlines()
    except OSError:
        return {}

    packages: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[=<>!~;\s\[]", line)[0].strip()
        if name:
            packages[name] = _pkg(name)
    return dict(sorted(packages.items(), key=lambda kv: kv[0].lower()))


async def _redis_server_version() -> str:
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        info = await client.info("server")
        await client.aclose()
        return info.get("redis_version", "unknown")
    except Exception:
        return "unavailable"


async def _worker_version() -> str | None:
    try:
        import redis.asyncio as aioredis

        from app.celery_app import WORKER_VERSION_KEY

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        value = await client.get(WORKER_VERSION_KEY)
        await client.aclose()
        return value.decode() if value else None
    except Exception:
        return None


@router.get("/versions", response_model=AdminVersionsResponse)
async def get_versions(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminVersionsResponse:
    settings = get_settings()

    pg_row = (await db.execute(text("SELECT version()"))).fetchone()
    pg_full = pg_row[0] if pg_row else "unknown"
    pg_version = pg_full.split()[1] if pg_full.startswith("PostgreSQL") else pg_full
    pg_source = "remote" if settings.postgres_dsn else "local docker"

    return AdminVersionsResponse(
        app=VERSION,
        python=platform.python_version(),
        redis_server=await _redis_server_version(),
        celery=_pkg("celery"),
        worker=await _worker_version(),
        postgres=pg_version,
        postgres_source=pg_source,
        backend_packages=_all_packages(),
    )


@router.get("/db-info", response_model=AdminDbInfoResponse)
async def get_db_info(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminDbInfoResponse:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    rev_row = (await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).fetchone()
    revision = rev_row[0] if rev_row else None

    try:
        cfg = Config("/app/alembic.ini")
        heads = set(ScriptDirectory.from_config(cfg).get_heads())
        is_at_head = revision in heads
    except Exception:
        is_at_head = False

    last_squash_at: str | None = None
    last_migrated_at: str | None = None
    try:
        meta_rows = (await db.execute(text("SELECT key, value FROM alembic_meta"))).fetchall()
        for key, value in meta_rows:
            if key == "last_squash_at":
                last_squash_at = value
            elif key == "last_migrated_at":
                last_migrated_at = value
    except Exception:
        pass

    return AdminDbInfoResponse(
        revision=revision,
        is_at_head=is_at_head,
        last_squash_at=last_squash_at,
        last_migrated_at=last_migrated_at,
    )


# ---------------------------------------------------------------------------
# Clerk ↔ DB reconciliation (superuser only)
# ---------------------------------------------------------------------------


class ReconcileClerkOnlyUser(BaseModel):
    clerk_user_id: str
    email: str
    display_name: str


class ReconcileDbOnlyUser(BaseModel):
    user_id: str
    email: str
    display_name: str
    clerk_errored: bool


class ReconcileReport(BaseModel):
    clerk_only: list[ReconcileClerkOnlyUser]
    db_only: list[ReconcileDbOnlyUser]


class BackfillRequest(BaseModel):
    role: Literal["user", "admin"] = "user"


class BackfillResponse(BaseModel):
    status: str
    user_id: str
    email: str


@router.get("/reconcile", response_model=ReconcileReport)
async def get_reconcile_report(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> ReconcileReport:
    clerk_users = await list_clerk_users()
    clerk_ids = {u["id"] for u in clerk_users}

    db_users = list(
        await db.scalars(
            select(User).where(
                User.clerk_user_id.is_not(None),
                User.deleted_at.is_(None),
                User.deletion_state.is_(None),
            )
        )
    )
    db_clerk_ids = {u.clerk_user_id for u in db_users}

    pending_ids = set(await db.scalars(select(PendingSignup.clerk_user_id)))

    clerk_only = [
        ReconcileClerkOnlyUser(
            clerk_user_id=u["id"],
            email=u["email"],
            display_name=u["display_name"],
        )
        for u in clerk_users
        if u["id"] not in db_clerk_ids and u["id"] not in pending_ids
    ]

    db_only = [
        ReconcileDbOnlyUser(
            user_id=str(u.id),
            email=u.email,
            display_name=u.display_name,
            clerk_errored=u.clerk_errored,
        )
        for u in db_users
        if u.clerk_user_id not in clerk_ids
    ]

    return ReconcileReport(clerk_only=clerk_only, db_only=db_only)


@router.post("/reconcile/backfill/{clerk_user_id}", response_model=BackfillResponse, status_code=201)
async def backfill_clerk_user(
    clerk_user_id: str,
    body: BackfillRequest = Body(default_factory=BackfillRequest),
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> BackfillResponse:
    existing = await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)))
    if existing:
        raise HTTPException(status_code=409, detail="User already exists in DB")

    clerk_data = await get_clerk_user(clerk_user_id)
    if clerk_data is None:
        raise HTTPException(status_code=404, detail="Clerk user not found")

    email = clerk_data["email"]
    display_name = clerk_data["display_name"]

    # Attach to a pre-created User (unclaimed invite) if one exists for this email.
    pre_user = await db.scalar(
        select(User).where(
            User.email == email,
            User.clerk_user_id.is_(None),
            User.deleted_at.is_(None),
        )
    )
    if pre_user:
        pre_user.clerk_user_id = clerk_user_id
        pre_user.display_name = display_name
        pre_user.is_active = True
        user = pre_user
        result_status = "attached"
    else:
        user = User(
            email=email,
            display_name=display_name,
            clerk_user_id=clerk_user_id,
            is_active=True,
            is_admin=(body.role == "admin"),
        )
        db.add(user)
        result_status = "created"

    await write_audit_log(
        db,
        event_type="user.backfilled",
        actor=admin,
        target_email=email,
        details={"clerk_user_id": clerk_user_id, "status": result_status},
    )
    await db.commit()
    await db.refresh(user)
    await set_user_metadata(clerk_user_id, {"status": "active"})

    log.info("backfill clerk_user_id=%s user_id=%s status=%s", clerk_user_id, user.id, result_status)
    return BackfillResponse(status=result_status, user_id=str(user.id), email=email)


# ---------------------------------------------------------------------------
# S3 orphan file audit (superuser only)
# ---------------------------------------------------------------------------


class S3OrphanFile(BaseModel):
    key: str
    size: int
    last_modified: str


class S3AuditResult(BaseModel):
    total_s3_keys: int
    total_db_paths: int
    orphaned_count: int
    orphaned_files: list[S3OrphanFile]
    not_applicable: bool


class S3AuditTaskStatus(BaseModel):
    status: str  # pending | running | complete | failed
    result: S3AuditResult | None = None
    error: str | None = None


class S3ScanResponse(BaseModel):
    task_id: str


class S3CleanupRequest(BaseModel):
    keys: list[str]


class S3CleanupResponse(BaseModel):
    deleted: int


@router.post("/s3-audit/scan", response_model=S3ScanResponse, status_code=202)
async def start_s3_audit_scan(
    _: User = Depends(require_superuser),
) -> S3ScanResponse:
    from app.tasks.s3_audit import run_s3_orphan_scan

    task = run_s3_orphan_scan.delay()
    log.info("s3_audit_scan_queued task_id=%s", task.id)
    return S3ScanResponse(task_id=task.id)


@router.get("/s3-audit/task/{task_id}", response_model=S3AuditTaskStatus)
async def get_s3_audit_task(
    task_id: str,
    _: User = Depends(require_superuser),
) -> S3AuditTaskStatus:
    from celery.result import AsyncResult

    result = AsyncResult(task_id)
    state = result.state
    if state in ("PENDING", "RECEIVED"):
        return S3AuditTaskStatus(status="pending")
    if state in ("STARTED", "RETRY"):
        return S3AuditTaskStatus(status="running")
    if state == "SUCCESS":
        return S3AuditTaskStatus(status="complete", result=S3AuditResult(**result.result))
    if state == "FAILURE":
        return S3AuditTaskStatus(status="failed", error=str(result.result))
    return S3AuditTaskStatus(status="pending")


@router.post("/s3-audit/cleanup", response_model=S3CleanupResponse)
async def cleanup_s3_orphans(
    body: S3CleanupRequest,
    admin: User = Depends(require_superuser),
) -> S3CleanupResponse:
    from app.services import storage

    if not body.keys:
        return S3CleanupResponse(deleted=0)

    deleted = 0
    for key in body.keys:
        try:
            storage._delete(key)
            deleted += 1
        except Exception as exc:
            log.warning("s3_cleanup_error key=%s error=%s", key, exc)

    log.info("s3_cleanup_complete admin_id=%s deleted=%d", admin.id, deleted)
    return S3CleanupResponse(deleted=deleted)
