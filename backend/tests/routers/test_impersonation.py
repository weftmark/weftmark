"""Tests for superuser impersonation (issue #972)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.yarn import Yarn


@pytest.mark.asyncio
async def test_impersonation_header_rejected_for_regular_user(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    """A non-superuser passing X-Impersonate-User-ID gets 403, not the target's data."""
    target = User(
        email="target-regular@example.com",
        display_name="Target",
        oidc_sub="target-regular-oidc",
    )
    db_session.add(target)
    await db_session.commit()

    r = await auth_client.get(
        "/api/yarn",
        headers={"X-Impersonate-User-ID": str(target.id)},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_impersonation_header_rejected_for_superuser_target(
    superuser_client: AsyncClient,
    db_session: AsyncSession,
):
    """A superuser cannot impersonate another superuser — returns 403."""
    target = User(
        email="target-super@example.com",
        display_name="Target Superuser",
        oidc_sub="target-super-oidc",
        is_admin=True,
        is_superuser=True,
    )
    db_session.add(target)
    await db_session.commit()

    r = await superuser_client.get(
        "/api/yarn",
        headers={"X-Impersonate-User-ID": str(target.id)},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_impersonation_data_scoped_to_target(
    superuser_client: AsyncClient,
    superuser_user: User,
    db_session: AsyncSession,
):
    """Superuser with header sees target user's data, not their own."""
    target = User(
        email="impersonation-target@example.com",
        display_name="Impersonated User",
        oidc_sub="impersonation-target-oidc",
    )
    db_session.add(target)
    await db_session.flush()

    target_yarn = Yarn(owner_id=target.id, brand="Target Brand", name="Target Yarn")
    db_session.add(target_yarn)
    await db_session.commit()

    r = await superuser_client.get(
        "/api/yarn",
        headers={"X-Impersonate-User-ID": str(target.id)},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Target Yarn"


@pytest.mark.asyncio
async def test_impersonation_header_absent_returns_own_data(
    superuser_client: AsyncClient,
    superuser_user: User,
    db_session: AsyncSession,
):
    """Without the header, get_effective_user behaves like get_current_user."""
    yarn = Yarn(owner_id=superuser_user.id, brand="Super Brand", name="Super Yarn")
    db_session.add(yarn)
    await db_session.commit()

    r = await superuser_client.get("/api/yarn")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Super Yarn"


@pytest.mark.asyncio
async def test_impersonation_audit_log_written(
    superuser_client: AsyncClient,
    superuser_user: User,
    test_user: User,
    db_session: AsyncSession,
):
    """POST /api/impersonation/start and /end write audit log entries."""
    actor_id = superuser_user.id
    target_id = test_user.id

    r = await superuser_client.post(
        "/api/impersonation/start",
        json={"target_user_id": str(target_id)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["target"]["id"] == str(target_id)

    started = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.event_type == "impersonation.started",
            AuditLog.actor_id == actor_id,
            AuditLog.target_user_id == target_id,
        )
    )
    assert started is not None

    r = await superuser_client.post(
        "/api/impersonation/end",
        json={"target_user_id": str(target_id), "duration_seconds": 42},
    )
    assert r.status_code == 200

    ended = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.event_type == "impersonation.ended",
            AuditLog.actor_id == actor_id,
            AuditLog.target_user_id == target_id,
        )
    )
    assert ended is not None
    assert ended.details is not None
    assert ended.details.get("duration_seconds") == 42


@pytest.mark.asyncio
async def test_impersonation_start_blocked_for_superuser_target(
    superuser_client: AsyncClient,
    db_session: AsyncSession,
):
    """Cannot start impersonation of a superuser via the start endpoint."""
    target = User(
        email="su-target@example.com",
        display_name="SU Target",
        oidc_sub="su-target-oidc",
        is_superuser=True,
        is_admin=True,
    )
    db_session.add(target)
    await db_session.commit()

    r = await superuser_client.post(
        "/api/impersonation/start",
        json={"target_user_id": str(target.id)},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_route_uses_real_identity(
    superuser_client: AsyncClient,
    test_user: User,
):
    """Admin routes use real superuser identity even with impersonation header."""
    r = await superuser_client.get(
        "/api/admin/users",
        headers={"X-Impersonate-User-ID": str(test_user.id)},
    )
    # superuser_user is also admin — real identity still resolves as admin
    assert r.status_code == 200
