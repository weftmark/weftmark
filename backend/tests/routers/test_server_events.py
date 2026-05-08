"""Tests for GET /api/admin/server-events endpoint."""

from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server_event import ServerEvent


def _make_event(
    event_type: str = "stack.startup",
    severity: str = "info",
    status: str = "closed",
    message: str | None = None,
    app_version: str = "1.0.0",
    started_at: datetime | None = None,
) -> ServerEvent:
    return ServerEvent(
        event_type=event_type,
        severity=severity,
        status=status,
        started_at=started_at or datetime.now(timezone.utc),
        app_version=app_version,
        message=message,
    )


# ---------------------------------------------------------------------------
# GET /api/admin/server-events
# ---------------------------------------------------------------------------


class TestListServerEvents:
    async def test_returns_200_admin(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/server-events")
        assert resp.status_code == 200

    async def test_returns_page_shape(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/server-events")
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/admin/server-events")
        assert resp.status_code in (401, 403)

    async def test_requires_admin(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/server-events")
        assert resp.status_code in (401, 403)

    async def test_returns_seeded_events(self, admin_client: AsyncClient, db_session: AsyncSession):
        db_session.add(_make_event("stack.startup", message="Test startup"))
        db_session.add(_make_event("health.check", message="Test check"))
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events")
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    async def test_event_fields_present(self, admin_client: AsyncClient, db_session: AsyncSession):
        db_session.add(_make_event("stack.startup", severity="info", status="closed", message="Boot"))
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events")
        item = resp.json()["items"][0]
        assert "id" in item
        assert "event_type" in item
        assert "severity" in item
        assert "status" in item
        assert "started_at" in item
        assert "ended_at" in item
        assert "elapsed_ms" in item
        assert "app_version" in item
        assert "message" in item

    async def test_ordered_newest_first(self, admin_client: AsyncClient, db_session: AsyncSession):
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        db_session.add(_make_event(started_at=now - timedelta(hours=2)))
        db_session.add(_make_event(started_at=now - timedelta(hours=1)))
        db_session.add(_make_event(started_at=now))
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events")
        items = resp.json()["items"]
        times = [item["started_at"] for item in items]
        assert times == sorted(times, reverse=True)

    async def test_filter_by_event_type(self, admin_client: AsyncClient, db_session: AsyncSession):
        db_session.add(_make_event("stack.startup"))
        db_session.add(_make_event("health.check"))
        db_session.add(_make_event("health.check"))
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events?event_type=health.check")
        data = resp.json()
        assert all(item["event_type"] == "health.check" for item in data["items"])

    async def test_filter_event_type_excludes_others(self, admin_client: AsyncClient, db_session: AsyncSession):
        db_session.add(_make_event("stack.startup"))
        db_session.add(_make_event("stack.shutdown"))
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events?event_type=stack.startup")
        data = resp.json()
        assert all(item["event_type"] == "stack.startup" for item in data["items"])

    async def test_pagination_page_size(self, admin_client: AsyncClient, db_session: AsyncSession):
        for _ in range(5):
            db_session.add(_make_event())
        await db_session.commit()

        resp = await admin_client.get("/api/admin/server-events?page_size=3")
        data = resp.json()
        assert len(data["items"]) <= 3

    async def test_pagination_page_2(self, admin_client: AsyncClient, db_session: AsyncSession):
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        for i in range(5):
            db_session.add(_make_event(started_at=now - timedelta(minutes=i)))
        await db_session.commit()

        resp1 = await admin_client.get("/api/admin/server-events?page=1&page_size=3")
        resp2 = await admin_client.get("/api/admin/server-events?page=2&page_size=3")
        ids1 = {item["id"] for item in resp1.json()["items"]}
        ids2 = {item["id"] for item in resp2.json()["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_total_reflects_filter(self, admin_client: AsyncClient, db_session: AsyncSession):
        db_session.add(_make_event("stack.startup"))
        db_session.add(_make_event("stack.startup"))
        db_session.add(_make_event("health.check"))
        await db_session.commit()

        resp_all = await admin_client.get("/api/admin/server-events")
        resp_filtered = await admin_client.get("/api/admin/server-events?event_type=stack.startup")
        assert resp_filtered.json()["total"] < resp_all.json()["total"]

    async def test_empty_result_when_no_events(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/server-events?event_type=nonexistent.type")
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
