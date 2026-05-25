"""Tests for data export endpoints.

POST   /api/users/me/data-export
GET    /api/users/me/data-export/status
GET    /api/users/me/data-export/download/{request_id}
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_export import UserExportRequest

# ---------------------------------------------------------------------------
# POST /api/users/me/data-export
# ---------------------------------------------------------------------------


class TestRequestDataExport:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/users/me/data-export")
        assert resp.status_code == 401

    async def test_queues_export_and_returns_202(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        with patch("app.tasks.export.run_user_export.delay") as mock_delay:
            resp = await auth_client.post("/api/users/me/data-export")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["request_id"] is not None
        mock_delay.assert_called_once()

    async def test_creates_db_row(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        with patch("app.tasks.export.run_user_export.delay"):
            resp = await auth_client.post("/api/users/me/data-export")
        request_id = uuid.UUID(resp.json()["request_id"])
        req = await db_session.get(UserExportRequest, request_id)
        assert req is not None
        assert req.user_id == test_user.id
        assert req.status == "pending"

    async def test_deduplicates_within_24h(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        existing = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc) - timedelta(hours=2),
            status="pending",
        )
        db_session.add(existing)
        await db_session.commit()

        with patch("app.tasks.export.run_user_export.delay") as mock_delay:
            resp = await auth_client.post("/api/users/me/data-export")
        assert resp.status_code == 202
        assert resp.json()["request_id"] == str(existing.id)
        mock_delay.assert_not_called()

    async def test_new_request_after_cooldown(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        old = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc) - timedelta(hours=25),
            status="complete",
            archive_path="exports/old.zip",
            expires_at=datetime.now(timezone.utc) + timedelta(days=6),
        )
        db_session.add(old)
        await db_session.commit()

        with patch("app.tasks.export.run_user_export.delay") as mock_delay:
            resp = await auth_client.post("/api/users/me/data-export")
        assert resp.status_code == 202
        assert resp.json()["request_id"] != str(old.id)
        mock_delay.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/users/me/data-export/status
# ---------------------------------------------------------------------------


class TestExportStatus:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/users/me/data-export/status")
        assert resp.status_code == 401

    async def test_returns_none_when_no_export(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me/data-export/status")
        assert resp.status_code == 200
        assert resp.json()["request_id"] is None

    async def test_returns_most_recent_pending(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc),
            status="pending",
        )
        db_session.add(req)
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/data-export/status")
        data = resp.json()
        assert data["status"] == "pending"
        assert data["request_id"] == str(req.id)

    async def test_returns_complete_with_expiry(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc),
            status="complete",
            archive_path="exports/test.zip",
            expires_at=expires,
        )
        db_session.add(req)
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/data-export/status")
        data = resp.json()
        assert data["status"] == "complete"
        assert data["expires_at"] is not None

    async def test_returns_most_recent_of_multiple(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        old = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc) - timedelta(days=2),
            status="complete",
            archive_path="exports/old.zip",
        )
        new = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc),
            status="pending",
        )
        db_session.add_all([old, new])
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/data-export/status")
        assert resp.json()["request_id"] == str(new.id)


# ---------------------------------------------------------------------------
# GET /api/users/me/data-export/download/{request_id}
# ---------------------------------------------------------------------------


class TestDownloadExport:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/users/me/data-export/download/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_unknown_id_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/users/me/data-export/download/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_pending_export_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc),
            status="pending",
        )
        db_session.add(req)
        await db_session.commit()

        resp = await auth_client.get(f"/api/users/me/data-export/download/{req.id}")
        assert resp.status_code == 404

    async def test_expired_export_returns_410(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc) - timedelta(days=8),
            status="complete",
            archive_path="exports/old.zip",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(req)
        await db_session.commit()

        resp = await auth_client.get(f"/api/users/me/data-export/download/{req.id}")
        assert resp.status_code == 410

    async def test_another_users_export_returns_404(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
    ):
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=admin_user.id,
            requested_at=datetime.now(timezone.utc),
            status="complete",
            archive_path="exports/admin.zip",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(req)
        await db_session.commit()

        resp = await auth_client.get(f"/api/users/me/data-export/download/{req.id}")
        assert resp.status_code == 404

    async def test_complete_export_streams_zip(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        req = UserExportRequest(
            id=uuid.uuid4(),
            user_id=test_user.id,
            requested_at=datetime.now(timezone.utc),
            status="complete",
            archive_path="exports/test.zip",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(req)
        await db_session.commit()

        fake_zip = b"PK\x03\x04"  # ZIP magic bytes
        with patch("app.services.storage.read_file", return_value=fake_zip):
            resp = await auth_client.get(f"/api/users/me/data-export/download/{req.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content == fake_zip
