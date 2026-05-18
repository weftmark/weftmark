"""Tests for POST /api/feedback and GET /api/admin/feedback endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feedback_payload(**overrides):
    return {
        "submission_type": "feedback",
        "body": "This is great!",
        "subject": "General feedback",
        "is_anonymous": False,
        "diagnostics": {
            "environment": "local instance",
            "page_url": "/projects",
            "user_agent": "Mozilla/5.0",
            "app_version": "0.159.0",
        },
        **overrides,
    }


# ---------------------------------------------------------------------------
# POST /api/feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSubmitFeedback:
    async def test_authenticated_user_can_submit(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/feedback", json=_feedback_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["submission_type"] == "feedback"
        assert data["dispatch_status"] in ("pending", "skipped")
        assert "id" in data

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/feedback", json=_feedback_payload())
        assert resp.status_code == 401

    async def test_missing_body_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/feedback", json={"submission_type": "feedback"})
        assert resp.status_code == 422

    async def test_invalid_submission_type_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/feedback", json=_feedback_payload(submission_type="invalid"))
        assert resp.status_code == 422

    async def test_all_submission_types_accepted(self, auth_client: AsyncClient):
        for stype in ("feedback", "feature_request", "bug_report"):
            resp = await auth_client.post("/api/feedback", json=_feedback_payload(submission_type=stype))
            assert resp.status_code == 201, f"Expected 201 for type={stype}, got {resp.status_code}"

    async def test_anonymous_flag_stores_correctly(self, auth_client: AsyncClient, db_session: AsyncSession):
        from app.models.feedback import UserFeedback

        resp = await auth_client.post("/api/feedback", json=_feedback_payload(is_anonymous=True))
        assert resp.status_code == 201
        row = await db_session.get(UserFeedback, uuid.UUID(resp.json()["id"]))
        assert row is not None
        assert row.is_anonymous is True
        # user_id still stored in DB even when anonymous (for admin recovery)
        assert row.user_id is not None

    async def test_user_id_stored_for_authenticated_user(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from app.models.feedback import UserFeedback

        resp = await auth_client.post("/api/feedback", json=_feedback_payload(is_anonymous=False))
        assert resp.status_code == 201
        row = await db_session.get(UserFeedback, uuid.UUID(resp.json()["id"]))
        assert row is not None
        assert row.user_id == test_user.id

    async def test_response_omits_user_email_when_anonymous(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/feedback", json=_feedback_payload(is_anonymous=True))
        assert resp.status_code == 201
        data = resp.json()
        assert "user_email" not in data or data.get("user_email") is None

    async def test_discussion_url_null_when_no_token(self, auth_client: AsyncClient):
        # Without GITHUB_FEEDBACK_TOKEN the dispatch is skipped
        resp = await auth_client.post("/api/feedback", json=_feedback_payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["github_discussion_url"] is None


# ---------------------------------------------------------------------------
# GET /api/admin/feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminListFeedback:
    async def test_admin_can_list(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/feedback")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/admin/feedback")
        assert resp.status_code == 401

    async def test_submission_appears_in_list(self, auth_client: AsyncClient, admin_client: AsyncClient):
        await auth_client.post("/api/feedback", json=_feedback_payload(body="Test body for list"))
        resp = await admin_client.get("/api/admin/feedback")
        items = resp.json()["items"]
        assert any(item["body"] == "Test body for list" for item in items)

    async def test_soft_deleted_excluded_by_default(self, auth_client: AsyncClient, admin_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload(body="to be deleted"))
        fid = sub.json()["id"]
        await admin_client.delete(f"/api/admin/feedback/{fid}")
        resp = await admin_client.get("/api/admin/feedback")
        ids = [i["id"] for i in resp.json()["items"]]
        assert fid not in ids

    async def test_include_deleted_query_param(self, auth_client: AsyncClient, admin_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload(body="soft deleted"))
        fid = sub.json()["id"]
        await admin_client.delete(f"/api/admin/feedback/{fid}")
        resp = await admin_client.get("/api/admin/feedback?include_deleted=true")
        ids = [i["id"] for i in resp.json()["items"]]
        assert fid in ids

    async def test_filter_by_type(self, auth_client: AsyncClient, admin_client: AsyncClient):
        await auth_client.post("/api/feedback", json=_feedback_payload(submission_type="bug_report"))
        resp = await admin_client.get("/api/admin/feedback?submission_type=bug_report")
        items = resp.json()["items"]
        assert all(i["submission_type"] == "bug_report" for i in items)


# ---------------------------------------------------------------------------
# GET /api/admin/feedback/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminFeedbackDetail:
    async def test_admin_can_get_detail(self, auth_client: AsyncClient, admin_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        resp = await admin_client.get(f"/api/admin/feedback/{fid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == fid

    async def test_not_found_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"/api/admin/feedback/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        resp = await auth_client.get(f"/api/admin/feedback/{fid}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/admin/feedback/{id}  (soft delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminSoftDeleteFeedback:
    async def test_soft_delete_sets_deleted_at(
        self, auth_client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession
    ):
        from app.models.feedback import UserFeedback

        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        resp = await admin_client.delete(f"/api/admin/feedback/{fid}")
        assert resp.status_code == 200
        await db_session.refresh(await db_session.get(UserFeedback, uuid.UUID(fid)))
        row = await db_session.get(UserFeedback, uuid.UUID(fid))
        assert row is not None
        assert row.deleted_at is not None

    async def test_not_found_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.delete(f"/api/admin/feedback/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        resp = await auth_client.delete(f"/api/admin/feedback/{fid}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/feedback/{id}/recover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminRecoverFeedback:
    async def test_recover_clears_deleted_at(
        self, auth_client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession
    ):
        from app.models.feedback import UserFeedback

        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        await admin_client.delete(f"/api/admin/feedback/{fid}")
        resp = await admin_client.post(f"/api/admin/feedback/{fid}/recover")
        assert resp.status_code == 200
        row = await db_session.get(UserFeedback, uuid.UUID(fid))
        assert row is not None
        assert row.deleted_at is None

    async def test_recover_non_deleted_returns_400(self, auth_client: AsyncClient, admin_client: AsyncClient):
        sub = await auth_client.post("/api/feedback", json=_feedback_payload())
        fid = sub.json()["id"]
        resp = await admin_client.post(f"/api/admin/feedback/{fid}/recover")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/feedback/{uuid.uuid4()}/recover")
        assert resp.status_code == 404
