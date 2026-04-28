"""Tests for the /api/projects router.

Coverage focus: the GET /{project_id}/drawdown endpoint added for the
WeavingPatternView feature (issue #8).
"""

import io
import tempfile
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.services import rendering

# ---------------------------------------------------------------------------
# WIF fixture — 4-shaft, 4-treadle, coloured warp/weft; renders correctly
# ---------------------------------------------------------------------------

_WIF = b"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

[WARP]
Threads=4
Units=Inches
Color=1

[WEFT]
Threads=4
Units=Inches
Color=2

[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=200,50,50
2=50,50,200

[THREADING]
1=1
2=2
3=3
4=4

[TIEUP]
1=1
2=2
3=3
4=4

[TREADLING]
1=1
2=2
3=3
4=4
"""


def _fake_png(width: int = 80, height: int = 80) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _insert_project(
    db_session: AsyncSession,
    owner: User,
    *,
    wif_path: str = "",
    weft_threads: int = 4,
) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Test Project",
        wif_filename="test.wif",
        wif_path=wif_path,
        has_treadling=True,
        num_shafts=4,
        num_treadles=4,
        weft_threads=weft_threads,
    )
    db_session.add(project)
    await db_session.commit()
    return project


# ---------------------------------------------------------------------------
# GET /api/projects
# ---------------------------------------------------------------------------


class TestListProjects:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/projects")
        assert resp.status_code == 200

    async def test_empty_list_when_no_projects(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/projects")
        assert resp.json() == []

    async def test_returns_created_project(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        await _insert_project(db_session, test_user, wif_path="p/x.wif")
        resp = await auth_client.get("/api/projects")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Project"

    async def test_does_not_return_deleted_project(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        project.soft_delete()
        await db_session.commit()
        resp = await auth_client.get("/api/projects")
        assert resp.json() == []

    async def test_does_not_return_other_users_projects(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        await _insert_project(db_session, admin_user, wif_path="p/other.wif")
        resp = await auth_client.get("/api/projects")
        assert resp.json() == []

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/projects")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}
# ---------------------------------------------------------------------------


class TestGetProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200

    async def test_returns_project_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        data = (await auth_client.get(f"/api/projects/{project.id}")).json()
        assert data["name"] == "Test Project"
        assert data["wif_filename"] == "test.wif"
        assert "has_preview" in data

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        project = await _insert_project(db_session, admin_user, wif_path="p/other.wif")
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/projects/{project_id}
# ---------------------------------------------------------------------------


class TestDeleteProject:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        resp = await auth_client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 204

    async def test_project_not_in_list_after_delete(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        await auth_client.delete(f"/api/projects/{project.id}")
        resp = await auth_client.get("/api/projects")
        assert resp.json() == []

    async def test_get_after_delete_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        await auth_client.delete(f"/api/projects/{project.id}")
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 404

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        project = await _insert_project(db_session, admin_user, wif_path="p/other.wif")
        resp = await auth_client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.delete(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_soft_deletes_in_db(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        await auth_client.delete(f"/api/projects/{project.id}")
        await db_session.refresh(project)
        assert project.deleted_at is not None


# ---------------------------------------------------------------------------
# GET /{project_id}/drawdown
# ---------------------------------------------------------------------------


class TestGetDrawdown:
    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="x.wif")
        resp = await client.get(f"/api/projects/{project.id}/drawdown")
        assert resp.status_code == 401

    async def test_returns_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/drawdown")
        assert resp.status_code == 404

    async def test_returns_404_for_other_users_project(
        self,
        db_session: AsyncSession,
        auth_client: AsyncClient,
        admin_user: User,
    ):
        other_project = await _insert_project(db_session, admin_user, wif_path="x.wif")
        resp = await auth_client.get(f"/api/projects/{other_project.id}/drawdown")
        assert resp.status_code == 404

    async def test_returns_404_when_no_wif_path(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="")
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")
        assert resp.status_code == 404

    async def test_renders_and_returns_png(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()

        project = await _insert_project(db_session, test_user, wif_path=tmp.name, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == b"\x89PNG"

    async def test_response_includes_pixels_per_row_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()

        project = await _insert_project(db_session, test_user, wif_path=tmp.name, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")

        assert resp.headers.get("X-Pixels-Per-Row") == str(rendering.DRAWDOWN_SCALE)

    async def test_response_includes_total_rows_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()

        project = await _insert_project(db_session, test_user, wif_path=tmp.name, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")

        assert resp.headers.get("X-Total-Rows") == "4"

    async def test_response_has_cache_control_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()

        project = await _insert_project(db_session, test_user, wif_path=tmp.name, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")

        assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"

    async def test_response_has_etag_header(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()

        project = await _insert_project(db_session, test_user, wif_path=tmp.name, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown")

        assert resp.headers.get("ETag") == f'"{project.id}"'


# ---------------------------------------------------------------------------
# POST /api/projects  (WIF upload)
# ---------------------------------------------------------------------------


class TestCreateProject:
    @pytest.fixture(autouse=True)
    def _use_tmp_upload_dir(self, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))

    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/projects",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Project"},
        )
        assert resp.status_code == 201

    async def test_returns_project_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/projects",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Project"},
        )
        data = resp.json()
        assert data["name"] == "My Project"
        assert data["wif_filename"] == "test.wif"
        assert "has_treadling" in data
        assert "lint_warnings" in data

    async def test_non_wif_extension_returns_400(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/projects",
            files={"wif_file": ("test.txt", b"not a wif", "text/plain")},
            data={"name": "My Project"},
        )
        assert resp.status_code == 400

    async def test_with_description(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/projects",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "Described Project", "description": "A test project"},
        )
        assert resp.status_code == 201
        assert resp.json()["description"] == "A test project"

    async def test_appears_in_list(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/projects",
            files={"wif_file": ("list.wif", _WIF, "application/octet-stream")},
            data={"name": "Listed Project"},
        )
        data = (await auth_client.get("/api/projects")).json()
        assert any(p["name"] == "Listed Project" for p in data)

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post(
            "/api/projects",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Project"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/preview
# ---------------------------------------------------------------------------


class TestGetPreview:
    async def test_returns_404_when_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        resp = await auth_client.get(f"/api/projects/{project.id}/preview")
        assert resp.status_code == 404

    async def test_other_users_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        project = await _insert_project(db_session, admin_user, wif_path="p/other.wif")
        resp = await auth_client.get(f"/api/projects/{project.id}/preview")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(
        self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, wif_path="p/x.wif")
        resp = await raw_client.get(f"/api/projects/{project.id}/preview")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/projects/{project_id}/generate-liftplan
# ---------------------------------------------------------------------------


class TestGenerateLiftplan:
    @pytest.fixture(autouse=True)
    def _use_tmp_upload_dir(self, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))

    async def _create_project_with_wif(
        self,
        db_session,
        user: User,
        *,
        has_treadling: bool = True,
        has_tieup: bool = True,
    ) -> Project:
        tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
        tmp.write(_WIF)
        tmp.close()
        project = Project(
            owner_id=user.id,
            name="Liftplan Project",
            wif_filename="test.wif",
            wif_path=tmp.name,
            has_treadling=has_treadling,
            has_tieup=has_tieup,
            has_liftplan=False,
            num_shafts=4,
            num_treadles=4,
        )
        db_session.add(project)
        await db_session.commit()
        return project

    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await self._create_project_with_wif(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/generate-liftplan")
        assert resp.status_code == 200

    async def test_has_liftplan_after_generation(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await self._create_project_with_wif(db_session, test_user)
        body = (await auth_client.post(f"/api/projects/{project.id}/generate-liftplan")).json()
        assert body["has_liftplan"] is True

    async def test_no_treadling_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await self._create_project_with_wif(db_session, test_user, has_treadling=False)
        resp = await auth_client.post(f"/api/projects/{project.id}/generate-liftplan")
        assert resp.status_code == 400

    async def test_no_tieup_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await self._create_project_with_wif(db_session, test_user, has_tieup=False)
        resp = await auth_client.post(f"/api/projects/{project.id}/generate-liftplan")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/generate-liftplan")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(
        self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await self._create_project_with_wif(db_session, test_user)
        resp = await raw_client.post(f"/api/projects/{project.id}/generate-liftplan")
        assert resp.status_code == 401
