import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt
from app.models.project import Project, ProjectPhoto
from app.models.user import User
from app.models.yarn import Yarn

# ---------------------------------------------------------------------------
# GET /api/admin/users/{user_id}/storage-report
# ---------------------------------------------------------------------------


async def _make_user_with_files(db_session: AsyncSession) -> User:
    user = User(
        email="storage-report-test@example.com",
        display_name="Storage Report User",
        oidc_sub="storage-report-sub",
    )
    db_session.add(user)
    await db_session.flush()

    draft = Draft(
        owner_id=user.id,
        name="Report Draft",
        wif_filename="report.wif",
        wif_path="drafts/abc/original.wif",
        preview_path="drafts/abc/preview.png",
    )
    db_session.add(draft)
    await db_session.flush()

    project = Project(
        owner_id=user.id,
        draft_id=draft.id,
        name="Report Project",
        project_type="treadle",
        status="active",
        total_picks=10,
    )
    db_session.add(project)
    await db_session.flush()

    photo = ProjectPhoto(
        project_id=project.id,
        file_path="projects/xyz/photo1.jpg",
        filename="photo1.jpg",
        file_size_bytes=100_000,
        display_order=1,
    )
    db_session.add(photo)

    yarn = Yarn(
        owner_id=user.id,
        brand="Test",
        name="Yarn",
        photo_path="yarn/abc/profile.jpg",
    )
    db_session.add(yarn)
    await db_session.commit()
    return user


class TestStorageReport:
    async def test_returns_200(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        assert resp.status_code == 200

    async def test_response_shape(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        data = resp.json()
        assert data["user_id"] == str(user.id)
        assert data["email"] == user.email
        assert isinstance(data["files"], list)
        assert isinstance(data["file_count"], int)
        assert isinstance(data["total_bytes"], int)
        assert isinstance(data["missing_from_s3_count"], int)

    async def test_includes_draft_wif(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        types = [f["entity_type"] for f in resp.json()["files"]]
        assert "draft_wif" in types

    async def test_includes_draft_preview(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        types = [f["entity_type"] for f in resp.json()["files"]]
        assert "draft_preview" in types

    async def test_includes_project_photo_with_size(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        photos = [f for f in resp.json()["files"] if f["entity_type"] == "project_photo"]
        assert len(photos) == 1
        assert photos[0]["size_bytes"] == 100_000

    async def test_includes_yarn_photo(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        types = [f["entity_type"] for f in resp.json()["files"]]
        assert "yarn_photo" in types

    async def test_file_count_matches_files_list(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        data = resp.json()
        assert data["file_count"] == len(data["files"])

    async def test_total_bytes_sums_known_sizes(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        data = resp.json()
        computed = sum(f["size_bytes"] for f in data["files"] if f["size_bytes"] is not None)
        assert data["total_bytes"] == computed

    async def test_fast_path_s3_verified_false(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        for f in resp.json()["files"]:
            assert f["s3_verified"] is False
            assert f["exists_in_s3"] is None

    async def test_empty_user_returns_empty(self, superuser_client: AsyncClient, db_session: AsyncSession):
        empty = User(email="empty-storage@example.com", display_name="Empty", oidc_sub="empty-sub")
        db_session.add(empty)
        await db_session.commit()
        resp = await superuser_client.get(f"/api/admin/users/{empty.id}/storage-report")
        data = resp.json()
        assert data["files"] == []
        assert data["file_count"] == 0
        assert data["total_bytes"] == 0

    async def test_nonexistent_user_returns_404(self, superuser_client: AsyncClient):
        resp = await superuser_client.get(f"/api/admin/users/{uuid.uuid4()}/storage-report")
        assert resp.status_code == 404

    async def test_admin_returns_403(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await admin_client.get(f"/api/admin/users/{user.id}/storage-report")
        assert resp.status_code == 403

    async def test_regular_user_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        user = await _make_user_with_files(db_session)
        resp = await auth_client.get(f"/api/admin/users/{user.id}/storage-report")
        assert resp.status_code == 403

    async def test_loom_version_photo_included(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = User(email="loom-photo-test@example.com", display_name="Loom", oidc_sub="loom-photo-sub")
        db_session.add(user)
        await db_session.flush()
        loom = Loom(owner_id=user.id, manufacturer="Schacht", model_name="Flip", loom_type="floor_loom")
        db_session.add(loom)
        await db_session.flush()
        version = LoomVersion(loom_id=loom.id, version_number=1, effective_date=date(2024, 1, 1))
        db_session.add(version)
        await db_session.flush()
        lvp = LoomVersionPhoto(
            loom_version_id=version.id,
            filename="photo.jpg",
            path="looms/abc/versions/xyz/photos/1.jpg",
            file_size_bytes=200_000,
        )
        db_session.add(lvp)
        await db_session.commit()
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        photos = [f for f in resp.json()["files"] if f["entity_type"] == "loom_version_photo"]
        assert len(photos) == 1
        assert photos[0]["size_bytes"] == 200_000

    async def test_loom_version_receipt_included(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = User(email="receipt-test@example.com", display_name="Receipt", oidc_sub="receipt-sub")
        db_session.add(user)
        await db_session.flush()
        loom = Loom(owner_id=user.id, manufacturer="Schacht", model_name="Wolf", loom_type="floor_loom")
        db_session.add(loom)
        await db_session.flush()
        version = LoomVersion(loom_id=loom.id, version_number=1, effective_date=date(2024, 1, 1))
        db_session.add(version)
        await db_session.flush()
        receipt = LoomVersionReceipt(
            loom_version_id=version.id,
            filename="receipt.pdf",
            path="looms/abc/versions/xyz/receipts/1.pdf",
        )
        db_session.add(receipt)
        await db_session.commit()
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        receipts = [f for f in resp.json()["files"] if f["entity_type"] == "loom_version_receipt"]
        assert len(receipts) == 1
        assert receipts[0]["size_bytes"] is None

    async def test_null_paths_not_included(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = User(email="null-paths@example.com", display_name="Null", oidc_sub="null-paths-sub")
        db_session.add(user)
        await db_session.flush()
        draft = Draft(
            owner_id=user.id,
            name="No Preview Draft",
            wif_filename="d.wif",
            wif_path="drafts/nop/original.wif",
            preview_path=None,
        )
        db_session.add(draft)
        await db_session.commit()
        resp = await superuser_client.get(f"/api/admin/users/{user.id}/storage-report")
        types = [f["entity_type"] for f in resp.json()["files"]]
        assert "draft_wif" in types
        assert "draft_preview" not in types
