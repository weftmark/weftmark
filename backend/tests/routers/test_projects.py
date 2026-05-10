import io
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.loom import Loom, LoomVersion, loom_tracking_flags
from app.models.project import Project
from app.models.project import ProjectPhoto as ProjectPhotoModel
from app.models.user import User


@pytest.fixture(autouse=True)
def _mock_preview_task(monkeypatch):
    """Prevent generate_drawdown_preview.delay() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.projects.generate_drawdown_preview", mock)
    return mock


@pytest.fixture(autouse=True)
def _mock_tile_task(monkeypatch):
    """Prevent prerender_drawdown_tiles.delay() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.projects.prerender_drawdown_tiles", mock)
    return mock


# ---------------------------------------------------------------------------
# Minimal WIF bytes used for all tests (has both treadling and liftplan)
# ---------------------------------------------------------------------------

_WIF = b"""[WIF]
Version=1.1
Date=April 1 1997
Developers=wif@mhsoft.com
Source Program=Test
Source Version=1.0

[CONTENTS]
COLOR PALETTE=true
WARP=true
WEFT=true
THREADING=true
TIEUP=true
TREADLING=true
LIFTPLAN=true

[COLOR PALETTE]
Range=0,255
Entries=2

[WARP]
Threads=4
Units=cm

[WEFT]
Threads=2
Units=cm

[THREADING]
1=1
2=2
3=3
4=4

[TIEUP]
1=1
2=2

[TREADLING]
1=1
2=2

[LIFTPLAN]
1=1
2=2
"""

_LOOM_PAYLOAD = {
    "loom_type": "floor_loom",
    "manufacturer": "Ashford",
    "model_name": "Table Loom 8",
    "effective_date": "2024-01-01",
    "num_shafts": 8,
    "num_treadles": 10,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_draft(db_session: AsyncSession, owner: User) -> Draft:
    """Insert a draft with WIF bytes written through the (mocked) storage layer."""
    import uuid

    import app.services.storage as storage

    draft_id = uuid.uuid4()
    wif_key = storage.save_wif(draft_id, "test.wif", _WIF)

    draft = Draft(
        id=draft_id,
        owner_id=owner.id,
        name="Test Draft",
        wif_filename="test.wif",
        wif_path=wif_key,
        has_treadling=True,
        has_liftplan=True,
        num_shafts=4,
        num_treadles=2,
        weft_threads=2,
    )
    db_session.add(draft)
    await db_session.commit()
    return draft


async def _insert_loom(db_session: AsyncSession, owner: User, **kwargs) -> tuple[Loom, LoomVersion]:
    loom_type = kwargs.get("loom_type", "floor_loom")
    lift, treadle = loom_tracking_flags(loom_type)
    loom = Loom(
        owner_id=owner.id,
        loom_type=loom_type,
        manufacturer=kwargs.get("manufacturer", "Ashford"),
        model_name=kwargs.get("model_name", "Table Loom 8"),
        supports_treadle_tracking=treadle,
        supports_lift_tracking=lift,
    )
    db_session.add(loom)
    await db_session.flush()
    version = LoomVersion(
        loom_id=loom.id,
        version_number=1,
        effective_date=date(2024, 1, 1),
        num_shafts=8,
        num_treadles=10,
    )
    db_session.add(version)
    await db_session.commit()
    return loom, version


async def _insert_active_project(db_session: AsyncSession, owner: User, draft: Draft, loom: Loom | None) -> Project:
    project = Project(
        owner_id=owner.id,
        draft_id=draft.id,
        loom_id=loom.id if loom else None,
        name="Existing project",
        project_type="treadle",
        status="active",
        current_pick=1,
        total_picks=2,
    )
    db_session.add(project)
    await db_session.commit()
    return project


def _base_payload(draft_id: str, **overrides) -> dict:
    return {
        "name": "My project",
        "draft_id": draft_id,
        "project_type": "treadle",
        **overrides,
    }


# ---------------------------------------------------------------------------
# TestCreateProject
# ---------------------------------------------------------------------------


class TestCreateProject:
    async def test_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id)))
        assert resp.status_code == 201

    async def test_returns_project_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id)))
        body = resp.json()
        assert body["name"] == "My project"
        assert body["project_type"] == "treadle"
        assert body["status"] == "active"
        assert body["current_pick"] == 1

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        resp = await client.post("/api/projects", json=_base_payload(str(draft.id)))
        assert resp.status_code == 401

    async def test_unknown_draft_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/projects", json=_base_payload(str(uuid.uuid4())))
        assert resp.status_code == 404

    async def test_invalid_project_type_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id), project_type="invalid"))
        assert resp.status_code == 400

    async def test_with_valid_loom_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id), loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_with_valid_loom_version_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_id=str(loom.id), loom_version_id=str(version.id)),
        )
        assert resp.status_code == 201
        assert resp.json()["loom_version_id"] == str(version.id)

    async def test_loom_version_from_other_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom_a, _ = await _insert_loom(db_session, test_user)
        loom_b, version_b = await _insert_loom(db_session, test_user, model_name="Other Loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_id=str(loom_a.id), loom_version_id=str(version_b.id)),
        )
        assert resp.status_code == 400

    async def test_loom_version_without_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        _, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_version_id=str(version.id)),
        )
        assert resp.status_code == 400

    async def test_second_active_project_on_same_loom_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, loom)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id), loom_id=str(loom.id)))
        assert resp.status_code == 409

    async def test_completed_project_does_not_block_new_one(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        existing = await _insert_active_project(db_session, test_user, draft, loom)
        existing.status = "completed"
        await db_session.commit()
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id), loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, admin_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id), loom_id=str(loom.id)))
        assert resp.status_code == 404

    async def test_dispatches_preview_when_draft_has_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        assert draft.drawdown_preview_path is None

        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id)))

        assert resp.status_code == 201
        mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_skips_preview_dispatch_when_draft_already_has_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        draft.drawdown_preview_path = "drawdown-previews/existing.png"
        await db_session.commit()

        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post("/api/projects", json=_base_payload(str(draft.id)))

        assert resp.status_code == 201
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestRestartProject
# ---------------------------------------------------------------------------


class TestRestartProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, loom)
        project.status = "abandoned"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 200

    async def test_status_becomes_active(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, loom)
        project.status = "abandoned"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.json()["status"] == "active"

    async def test_preserves_current_pick(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, loom)
        project.status = "abandoned"
        project.current_pick = 2
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.json()["current_pick"] == 2

    async def test_completed_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 400

    async def test_active_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 400

    async def test_loom_conflict_returns_409(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        abandoned = await _insert_active_project(db_session, test_user, draft, loom)
        abandoned.status = "abandoned"
        await db_session.commit()
        await _insert_active_project(db_session, test_user, draft, loom)
        resp = await auth_client.post(f"/api/projects/{abandoned.id}/restart")
        assert resp.status_code == 409

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 401

    async def test_dispatches_preview_when_draft_has_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "abandoned"
        await db_session.commit()
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 200
        mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_skips_preview_dispatch_when_draft_already_has_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        draft.drawdown_preview_path = "drawdown-previews/existing.png"
        await db_session.commit()
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "abandoned"
        await db_session.commit()
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post(f"/api/projects/{project.id}/restart")
        assert resp.status_code == 200
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestCloneProject
# ---------------------------------------------------------------------------


async def _insert_project_with_status(
    db_session: AsyncSession, owner: User, draft: "Draft", loom: "Loom | None", status: str
) -> Project:
    project = Project(
        owner_id=owner.id,
        draft_id=draft.id,
        loom_id=loom.id if loom else None,
        name="Original project",
        project_type="treadle",
        status=status,
        current_pick=3,
        total_picks=10,
    )
    db_session.add(project)
    await db_session.commit()
    return project


class TestCloneProject:
    async def test_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 201

    async def test_clone_starts_at_pick_1(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.json()["current_pick"] == 1

    async def test_clone_is_active(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.json()["status"] == "active"

    async def test_clone_copies_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "abandoned")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        body = resp.json()
        assert body["name"] == project.name
        assert body["project_type"] == project.project_type
        assert body["draft_id"] == str(project.draft_id)

    async def test_can_clone_active_project(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "active")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 201

    async def test_loom_conflict_returns_409(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        completed = await _insert_project_with_status(db_session, test_user, draft, loom, "completed")
        await _insert_active_project(db_session, test_user, draft, loom)
        resp = await auth_client.post(f"/api/projects/{completed.id}/clone")
        assert resp.status_code == 409

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/clone")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 401

    async def test_dispatches_preview_when_draft_has_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 201
        mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_skips_preview_dispatch_when_draft_already_has_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        draft.drawdown_preview_path = "drawdown-previews/existing.png"
        await db_session.commit()
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 201
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Photo helpers
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 10, height: int = 10) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width: int = 10, height: int = 10) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# TestResizeToJpeg
# ---------------------------------------------------------------------------


class TestResizeToJpeg:
    def test_returns_bytes(self):
        from app.services.images import resize_to_jpeg

        assert isinstance(resize_to_jpeg(_make_jpeg()), bytes)

    def test_output_is_jpeg(self):
        from app.services.images import resize_to_jpeg

        result = resize_to_jpeg(_make_jpeg())
        assert PILImage.open(io.BytesIO(result)).format == "JPEG"

    def test_png_input_converted_to_jpeg(self):
        from app.services.images import resize_to_jpeg

        result = resize_to_jpeg(_make_png())
        assert PILImage.open(io.BytesIO(result)).format == "JPEG"

    def test_large_image_resized_to_max_px(self):
        from app.services.images import resize_to_jpeg

        result = resize_to_jpeg(_make_jpeg(3000, 3000), max_px=2048)
        assert max(PILImage.open(io.BytesIO(result)).size) <= 2048

    def test_small_image_not_upscaled(self):
        from app.services.images import resize_to_jpeg

        result = resize_to_jpeg(_make_jpeg(50, 50))
        assert PILImage.open(io.BytesIO(result)).size == (50, 50)


# ---------------------------------------------------------------------------
# TestProjectPhotos
# ---------------------------------------------------------------------------


class TestProjectPhotos:
    @pytest.fixture(autouse=True)
    def _use_tmp_upload_dir(self, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))

    async def test_upload_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 201

    async def test_upload_returns_schema(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("shot.jpg", _make_jpeg(), "image/jpeg")},
        )
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "shot.jpg"
        assert body["display_order"] == 1

    async def test_second_upload_increments_display_order(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("a.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("b.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.json()["display_order"] == 2

    async def test_png_stored_as_jpeg(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.png", _make_png(), "image/png")},
        )
        assert resp.status_code == 201
        photo_id = resp.json()["id"]
        get_resp = await auth_client.get(f"/api/projects/{project.id}/photos/{photo_id}")
        assert get_resp.status_code == 200
        assert PILImage.open(io.BytesIO(get_resp.content)).format == "JPEG"

    async def test_upload_too_large_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        big = b"X" * (26 * 1024 * 1024)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", big, "image/jpeg")},
        )
        assert resp.status_code == 400

    async def test_upload_wrong_type_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_upload_cap_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        for i in range(20):
            photo = ProjectPhotoModel(
                project_id=project.id,
                file_path=f"projects/{project.id}/photos/photo{i}.jpg",
                filename=f"photo{i}.jpg",
                file_size_bytes=1024,
                display_order=i + 1,
            )
            db_session.add(photo)
        await db_session.commit()
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 400

    async def test_get_photo_returns_image(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        upload = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        photo_id = upload.json()["id"]
        resp = await auth_client.get(f"/api/projects/{project.id}/photos/{photo_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")

    async def test_get_photo_cross_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        proj1 = await _insert_active_project(db_session, test_user, draft, None)
        proj2 = await _insert_active_project(db_session, test_user, draft, None)
        upload = await auth_client.post(
            f"/api/projects/{proj1.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        photo_id = upload.json()["id"]
        resp = await auth_client.get(f"/api/projects/{proj2.id}/photos/{photo_id}")
        assert resp.status_code == 404

    async def test_delete_photo_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        upload = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        photo_id = upload.json()["id"]
        resp = await auth_client.delete(f"/api/projects/{project.id}/photos/{photo_id}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.delete(f"/api/projects/{project.id}/photos/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_photos_appear_in_detail(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("snap.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200
        photos = resp.json()["photos"]
        assert len(photos) == 1
        assert photos[0]["filename"] == "snap.jpg"

    async def test_upload_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 401

    async def test_get_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/photos/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_delete_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.delete(f"/api/projects/{project.id}/photos/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_upload_records_file_size_bytes(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 201
        photo_id = uuid.UUID(resp.json()["id"])
        from sqlalchemy import select as sa_select

        photo = await db_session.scalar(sa_select(ProjectPhotoModel).where(ProjectPhotoModel.id == photo_id))
        assert photo is not None
        assert photo.file_size_bytes > 0


# ---------------------------------------------------------------------------
# TestStorageQuota
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStorageQuota:
    async def test_quota_exceeded_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from app.services.storage_quota import MAX_USER_STORAGE_BYTES

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        # Insert a photo that consumes the entire quota
        photo = ProjectPhotoModel(
            project_id=project.id,
            file_path=f"projects/{project.id}/photos/big.jpg",
            filename="big.jpg",
            file_size_bytes=MAX_USER_STORAGE_BYTES,
            display_order=1,
        )
        db_session.add(photo)
        await db_session.commit()

        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 400
        assert "Storage limit" in resp.json()["detail"]

    async def test_get_user_storage_used_sums_project_photos(self, db_session: AsyncSession, test_user: User):
        from app.services.storage_quota import get_user_storage_used

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        for i in range(3):
            db_session.add(
                ProjectPhotoModel(
                    project_id=project.id,
                    file_path=f"projects/{project.id}/photos/p{i}.jpg",
                    filename=f"p{i}.jpg",
                    file_size_bytes=100_000,
                    display_order=i,
                )
            )
        await db_session.commit()

        used = await get_user_storage_used(test_user.id, db_session)
        assert used == 300_000


# ---------------------------------------------------------------------------
# TestGetProject
# ---------------------------------------------------------------------------


class TestGetProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200

    async def test_returns_project_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}")).json()
        assert body["name"] == project.name
        assert body["project_type"] == "treadle"
        assert body["status"] == "active"
        assert "photos" in body
        assert "draft_name" in body

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = await _insert_draft(db_session, admin_user)
        project = await _insert_active_project(db_session, admin_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 401

    async def test_loom_num_treadles_null_without_loom(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}")).json()
        assert body["loom_num_treadles"] is None
        assert body["loom_num_shafts"] is None

    async def test_loom_num_treadles_populated_with_loom_version(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, version = await _insert_loom(db_session, test_user)
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            loom_id=loom.id,
            loom_version_id=version.id,
            name="Test project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=2,
        )
        db_session.add(project)
        await db_session.commit()
        body = (await auth_client.get(f"/api/projects/{project.id}")).json()
        assert body["loom_num_treadles"] == version.num_treadles
        assert body["loom_num_shafts"] == version.num_shafts

    async def test_dispatches_preview_when_draft_has_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200
        mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_skips_preview_dispatch_when_draft_already_has_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from unittest.mock import MagicMock, patch

        draft = await _insert_draft(db_session, test_user)
        draft.drawdown_preview_path = "drawdown-previews/existing.png"
        await db_session.commit()
        project = await _insert_active_project(db_session, test_user, draft, None)
        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            mock_task.delay = MagicMock()
            resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestListProjects
# ---------------------------------------------------------------------------


class TestListProjects:
    async def test_returns_empty_list(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_projects(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, None)
        data = (await auth_client.get("/api/projects")).json()
        assert len(data) >= 1

    async def test_filter_by_draft_id(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, None)
        data = (await auth_client.get(f"/api/projects?draft_id={draft.id}")).json()
        assert all(p["draft_id"] == str(draft.id) for p in data)
        assert len(data) == 1

    async def test_filter_by_loom_id(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, loom)
        await _insert_active_project(db_session, test_user, draft, None)
        data = (await auth_client.get(f"/api/projects?loom_id={loom.id}")).json()
        assert len(data) == 1
        assert data[0]["loom_id"] == str(loom.id)

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/projects")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestRenameProject
# ---------------------------------------------------------------------------


class TestRenameProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}", json={"name": "Renamed"})
        assert resp.status_code == 200

    async def test_renames_project(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.patch(f"/api/projects/{project.id}", json={"name": "New Name"})).json()
        assert body["name"] == "New Name"

    async def test_empty_name_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}", json={"name": "   "})
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/projects/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.patch(f"/api/projects/{project.id}", json={"name": "x"})
        assert resp.status_code == 401

    async def test_updates_notes(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.patch(f"/api/projects/{project.id}", json={"notes": "my notes"})).json()
        assert body["notes"] == "my notes"

    async def test_notes_only_preserves_name(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        original_name = project.name
        body = (await auth_client.patch(f"/api/projects/{project.id}", json={"notes": "n"})).json()
        assert body["name"] == original_name

    async def test_no_fields_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}", json={})
        assert resp.status_code == 400

    async def test_sets_hide_unused_shafts_treadles(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (
            await auth_client.patch(f"/api/projects/{project.id}", json={"hide_unused_shafts_treadles": True})
        ).json()
        assert body["hide_unused_shafts_treadles"] is True

    async def test_clears_hide_unused_shafts_treadles(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.patch(f"/api/projects/{project.id}", json={"hide_unused_shafts_treadles": True})
        body = (
            await auth_client.patch(f"/api/projects/{project.id}", json={"hide_unused_shafts_treadles": False})
        ).json()
        assert body["hide_unused_shafts_treadles"] is False


# ---------------------------------------------------------------------------
# TestHideUnusedShaftsTreadlesInheritance
# ---------------------------------------------------------------------------


class TestHideUnusedShaftsTreadlesInheritance:
    async def test_project_inherits_user_default_off(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """New project inherits hide_unused_shafts_treadles=False (user default)."""
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            warp_threads=4,
            weft_threads=4,
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await auth_client.post(
            "/api/projects",
            json={"name": "P", "draft_id": str(draft_id), "project_type": "treadle"},
        )
        assert resp.status_code == 201
        assert resp.json()["hide_unused_shafts_treadles"] is False

    async def test_project_inherits_user_default_on(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """New project inherits hide_unused_shafts_treadles=True when user default is on."""
        import app.services.storage as storage

        test_user.hide_unused_shafts_treadles = True
        await db_session.commit()

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            warp_threads=4,
            weft_threads=4,
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await auth_client.post(
            "/api/projects",
            json={"name": "P", "draft_id": str(draft_id), "project_type": "treadle"},
        )
        assert resp.status_code == 201
        assert resp.json()["hide_unused_shafts_treadles"] is True


# ---------------------------------------------------------------------------
# TestDeleteProject
# ---------------------------------------------------------------------------


class TestDeleteProject:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 204

    async def test_not_in_list_after_delete(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.delete(f"/api/projects/{project.id}")
        data = (await auth_client.get("/api/projects")).json()
        assert all(p["id"] != str(project.id) for p in data)

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.delete(f"/api/projects/{project.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestStepProject
# ---------------------------------------------------------------------------


class TestStepProject:
    async def test_advance_increments_pick(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})).json()
        assert body["current_pick"] == 2

    async def test_reverse_decrements_pick(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.current_pick = 2
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "reverse"})).json()
        assert body["current_pick"] == 1

    async def test_reverse_at_first_pick_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "reverse"})
        assert resp.status_code == 400

    async def test_advance_past_last_pick_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.current_pick = project.total_picks + 1
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        assert resp.status_code == 400

    async def test_invalid_direction_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "sideways"})
        assert resp.status_code == 400

    async def test_completed_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/step", json={"direction": "advance"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        assert resp.status_code == 401

    async def test_response_is_lightweight(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})).json()
        assert set(body.keys()) == {"current_pick", "total_picks"}

    async def test_logs_step_to_database(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        from sqlalchemy import select

        from app.models.project import ProjectStep

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        step = await db_session.scalar(select(ProjectStep).where(ProjectStep.project_id == project.id))
        assert step is not None
        assert step.event_type == "advance"
        assert step.from_pick == 1
        assert step.to_pick == 2

    async def test_rapid_advances_produce_unique_increments(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Each step call must increment current_pick by exactly 1 with no duplicates.
        True DB concurrency is serialized by SELECT FOR UPDATE in the router; here
        we verify sequential rapid advances produce monotonically unique picks."""
        draft = await _insert_draft(db_session, test_user)
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Rapid tap project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()
        picks = []
        for _ in range(4):
            resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
            assert resp.status_code == 200
            picks.append(resp.json()["current_pick"])
        assert picks == sorted(set(picks)), f"Duplicate or out-of-order picks: {picks}"


# ---------------------------------------------------------------------------
# TestJumpProject
# ---------------------------------------------------------------------------


class TestJumpProject:
    async def test_jumps_to_pick(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": 2})).json()
        assert body["current_pick"] == 2

    async def test_clamps_above_total_plus_one(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": 999})).json()
        assert body["current_pick"] == project.total_picks + 1

    async def test_clamps_below_one(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": 0})).json()
        assert body["current_pick"] == 1

    async def test_completed_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": 1})
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/jump", json={"pick": 1})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCompleteProject
# ---------------------------------------------------------------------------


class TestCompleteProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 200

    async def test_status_becomes_completed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/complete")).json()
        assert body["status"] == "completed"

    async def test_sets_completed_at(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(f"/api/projects/{project.id}/complete")
        await db_session.refresh(project)
        assert project.completed_at is not None

    async def test_already_completed_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/complete")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestAbandonProject
# ---------------------------------------------------------------------------


class TestAbandonProject:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/abandon")
        assert resp.status_code == 200

    async def test_status_becomes_abandoned(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/abandon")).json()
        assert body["status"] == "abandoned"

    async def test_sets_abandoned_at(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(f"/api/projects/{project.id}/abandon")
        await db_session.refresh(project)
        assert project.abandoned_at is not None

    async def test_already_abandoned_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "abandoned"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/abandon")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/abandon")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/abandon")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestAssignLoom
# ---------------------------------------------------------------------------


class TestAssignLoom:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom, _ = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/assign-loom", json={"loom_id": str(loom.id)})
        assert resp.status_code == 200

    async def test_assigns_loom(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom, _ = await _insert_loom(db_session, test_user)
        body = (
            await auth_client.post(f"/api/projects/{project.id}/assign-loom", json={"loom_id": str(loom.id)})
        ).json()
        assert body["loom_id"] == str(loom.id)

    async def test_assigns_with_version(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom, version = await _insert_loom(db_session, test_user)
        body = (
            await auth_client.post(
                f"/api/projects/{project.id}/assign-loom",
                json={"loom_id": str(loom.id), "loom_version_id": str(version.id)},
            )
        ).json()
        assert body["loom_version_id"] == str(version.id)

    async def test_assign_loom_version_returns_loom_counts(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom, version = await _insert_loom(db_session, test_user)
        body = (
            await auth_client.post(
                f"/api/projects/{project.id}/assign-loom",
                json={"loom_id": str(loom.id), "loom_version_id": str(version.id)},
            )
        ).json()
        assert body["loom_num_treadles"] == version.num_treadles
        assert body["loom_num_shafts"] == version.num_shafts

    async def test_wrong_version_for_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom_a, _ = await _insert_loom(db_session, test_user)
        _, version_b = await _insert_loom(db_session, test_user, model_name="Other Loom")
        resp = await auth_client.post(
            f"/api/projects/{project.id}/assign-loom",
            json={"loom_id": str(loom_a.id), "loom_version_id": str(version_b.id)},
        )
        assert resp.status_code == 400

    async def test_already_has_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, loom)
        resp = await auth_client.post(f"/api/projects/{project.id}/assign-loom", json={"loom_id": str(loom.id)})
        assert resp.status_code == 400

    async def test_not_active_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        loom, _ = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/assign-loom", json={"loom_id": str(loom.id)})
        assert resp.status_code == 400

    async def test_loom_conflict_returns_409(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, loom)
        project2 = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project2.id}/assign-loom", json={"loom_id": str(loom.id)})
        assert resp.status_code == 409

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        other_loom, _ = await _insert_loom(db_session, admin_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/assign-loom", json={"loom_id": str(other_loom.id)})
        assert resp.status_code == 404

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/assign-loom", json={"loom_id": str(uuid.uuid4())})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestGetPicks
# ---------------------------------------------------------------------------


class TestGetPicks:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}/picks")
        assert resp.status_code == 200

    async def test_returns_picks_data(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/picks")).json()
        assert "project_type" in body
        assert "total_picks" in body
        assert "picks" in body
        assert isinstance(body["picks"], list)
        assert "has_weft_colors" in body

    async def test_returns_correct_pick_count(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/picks")).json()
        assert body["total_picks"] == len(body["picks"])

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/picks")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/picks")
        assert resp.status_code == 401

    async def test_lift_project_uses_modified_wif(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await _insert_draft(db_session, test_user)
        modified_key = f"drafts/{draft.id}/modified.wif"
        mock_storage[modified_key] = _WIF
        draft.wif_modified_path = modified_key
        await db_session.commit()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Lift project",
            project_type="lift",
            status="active",
            current_pick=1,
            total_picks=2,
        )
        db_session.add(project)
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/picks")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unsupported loom type — project creation and assignment
# ---------------------------------------------------------------------------


class TestUnsupportedLoomType:
    async def test_unsupported_loom_type_blocks_create(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user, loom_type="rigid_heddle")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_id=str(loom.id)),
        )
        assert resp.status_code == 422

    async def test_dobby_loom_blocks_create(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user, loom_type="dobby")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_id=str(loom.id)),
        )
        assert resp.status_code == 422

    async def test_floor_loom_allowed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user, loom_type="floor_loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), loom_id=str(loom.id)),
        )
        assert resp.status_code == 201

    async def test_table_loom_allowed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user, loom_type="table_loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(str(draft.id), project_type="lift", loom_id=str(loom.id)),
        )
        assert resp.status_code == 201

    async def test_unsupported_loom_type_blocks_assign(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        loom, _ = await _insert_loom(db_session, test_user, loom_type="inkle")
        resp = await auth_client.post(
            f"/api/projects/{project.id}/assign-loom",
            json={"loom_id": str(loom.id)},
        )
        assert resp.status_code == 422
