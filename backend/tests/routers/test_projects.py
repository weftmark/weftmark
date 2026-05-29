import io
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from PIL import Image as PILImage
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.loom import Loom, LoomVersion, loom_tracking_flags
from app.models.project import Project, ProjectDraft
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
    """Prevent prerender_project_tiles.delay/apply_async() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.projects.prerender_project_tiles", mock)
    return mock


@pytest.fixture(autouse=True)
def _mock_project_preview_task(monkeypatch):
    """Prevent generate_project_drawdown_preview.delay() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.projects.generate_project_drawdown_preview", mock)
    return mock


@pytest.fixture(autouse=True)
def _mock_project_svg_task(monkeypatch):
    """Prevent generate_project_drawdown_svg.delay() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.projects.generate_project_drawdown_svg", mock)
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
Units=centimeters

[WEFT]
Threads=2
Units=centimeters

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

# Renderable WIF: includes [WEAVING] section and 4 weft threads required by PyWeaving.
# Used only by _insert_project_with_wif so existing tests are unaffected.
_WIF_RENDERABLE = b"""[WIF]
Version=1.1
Date=April 1 1997
Developers=wif@mhsoft.com
Source Program=Test
Source Version=1.0

[CONTENTS]
COLOR PALETTE=true
COLOR TABLE=true
WEAVING=true
WARP=true
WEFT=true
THREADING=true
TIEUP=true
TREADLING=true

[COLOR PALETTE]
Range=0,255
Entries=2

[COLOR TABLE]
1=255,255,255
2=0,0,0

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

[WARP]
Threads=4
Units=centimeters
Color=1

[WEFT]
Threads=4
Units=centimeters
Color=2

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
        loom_id=loom.id if loom else None,
        name="Existing project",
        project_type="treadle",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    seq = ProjectDraft(
        project_id=project.id,
        draft_id=draft.id,
        position=1,
        repeats=1,
        current_pick=1,
    )
    db_session.add(seq)
    await db_session.commit()
    return project


async def _get_seq_entry(db_session: AsyncSession, project: Project) -> ProjectDraft:
    from sqlalchemy import select as _sa_select

    entry = await db_session.scalar(
        _sa_select(ProjectDraft).where(ProjectDraft.project_id == project.id, ProjectDraft.position == 1)
    )
    assert entry is not None
    return entry


def _base_payload(**overrides) -> dict:
    return {
        "name": "My project",
        **overrides,
    }


# ---------------------------------------------------------------------------
# TestCreateProject
# ---------------------------------------------------------------------------


class TestCreateProject:
    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/projects", json=_base_payload())
        assert resp.status_code == 201

    async def test_returns_project_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/projects", json=_base_payload())
        body = resp.json()
        assert body["name"] == "My project"
        assert body["project_type"] is None  # null until loom assigned
        assert body["status"] == "created"
        assert body["current_pick"] == 0  # no sequence yet

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/projects", json=_base_payload())
        assert resp.status_code == 401

    async def test_with_valid_loom_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        loom, _ = await _insert_loom(db_session, test_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_with_valid_loom_version_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        loom, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom.id), loom_version_id=str(version.id)),
        )
        assert resp.status_code == 201
        assert resp.json()["loom_version_id"] == str(version.id)

    async def test_loom_version_from_other_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        loom_a, _ = await _insert_loom(db_session, test_user)
        loom_b, version_b = await _insert_loom(db_session, test_user, model_name="Other Loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom_a.id), loom_version_id=str(version_b.id)),
        )
        assert resp.status_code == 400

    async def test_loom_version_without_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_version_id=str(version.id)),
        )
        assert resp.status_code == 400

    async def test_second_active_project_on_same_loom_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        await _insert_active_project(db_session, test_user, draft, loom)
        resp = await auth_client.post("/api/projects", json=_base_payload(loom_id=str(loom.id)))
        assert resp.status_code == 409

    async def test_completed_project_does_not_block_new_one(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        existing = await _insert_active_project(db_session, test_user, draft, loom)
        existing.status = "completed"
        await db_session.commit()
        resp = await auth_client.post("/api/projects", json=_base_payload(loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        loom, _ = await _insert_loom(db_session, admin_user)
        resp = await auth_client.post("/api/projects", json=_base_payload(loom_id=str(loom.id)))
        assert resp.status_code == 404


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
        assert resp.json()["status"] == "created"

    async def test_preserves_current_pick(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, loom)
        project.status = "abandoned"
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2
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


# ---------------------------------------------------------------------------
# TestCloneProject
# ---------------------------------------------------------------------------


async def _insert_project_with_status(
    db_session: AsyncSession, owner: User, draft: "Draft", loom: "Loom | None", status: str
) -> Project:
    project = Project(
        owner_id=owner.id,
        loom_id=loom.id if loom else None,
        name="Original project",
        project_type="treadle",
        status=status,
    )
    db_session.add(project)
    await db_session.flush()
    seq = ProjectDraft(
        project_id=project.id,
        draft_id=draft.id,
        position=1,
        repeats=1,
        current_pick=1,
    )
    db_session.add(seq)
    await db_session.commit()
    return project


class TestCloneProject:
    async def test_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.status_code == 201

    async def test_clone_starts_at_pick_0(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.json()["current_pick"] == 0  # clone resets all picks to 0

    async def test_clone_is_created(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        assert resp.json()["status"] == "created"

    async def test_clone_copies_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "abandoned")
        resp = await auth_client.post(f"/api/projects/{project.id}/clone")
        body = resp.json()
        assert body["name"] == project.name
        assert body["project_type"] == project.project_type
        assert body["draft_id"] == str(draft.id)

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

    async def test_spoofed_content_type_rejected(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        # Regression: garbage bytes claiming to be JPEG must be rejected via PIL
        # magic-byte check, not the client-supplied Content-Type header.
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/photos",
            files={"file": ("evil.jpg", b"not an image at all", "image/jpeg")},
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
        project = await _insert_active_project(db_session, test_user, draft, loom)
        project.loom_version_id = version.id
        await db_session.commit()
        body = (await auth_client.get(f"/api/projects/{project.id}")).json()
        assert body["loom_num_treadles"] == version.num_treadles
        assert body["loom_num_shafts"] == version.num_shafts

    async def test_dispatches_preview_when_active_draft_has_no_preview(
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

    async def test_skips_preview_dispatch_when_active_draft_has_preview(
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

        resp = await auth_client.post("/api/projects", json={"name": "P"})
        assert resp.status_code == 201
        assert resp.json()["hide_unused_shafts_treadles"] is False

    async def test_project_inherits_user_default_on(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """New project inherits hide_unused_shafts_treadles=True when user default is on."""
        test_user.hide_unused_shafts_treadles = True
        await db_session.commit()

        resp = await auth_client.post("/api/projects", json={"name": "P"})
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
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "reverse"})).json()
        assert body["current_pick"] == 1

    async def test_reverse_at_first_pick_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 0
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "reverse"})
        assert resp.status_code == 400

    async def test_advance_past_last_pick_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # == section_total (weft_threads=2, repeats=1)
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

    async def test_response_has_expected_keys(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})).json()
        assert set(body.keys()) == {
            "current_pick",
            "total_picks",
            "position",
            "aggregate_current_pick",
            "aggregate_total_picks",
            "current_item",
            "num_items",
        }

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
            name="Rapid tap project",
            project_type="treadle",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        seq = ProjectDraft(
            project_id=project.id,
            draft_id=draft.id,
            position=1,
            repeats=5,  # section_total = 2 * 5 = 10
            current_pick=0,
        )
        db_session.add(seq)
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

    async def test_clamps_above_section_total(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": 999})).json()
        assert body["current_pick"] == 2  # clamped to section_total (weft=2, repeats=1)

    async def test_clamps_below_zero(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.post(f"/api/projects/{project.id}/jump", json={"pick": -5})).json()
        assert body["current_pick"] == 0  # clamped to 0

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
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total (weft=2, repeats=1) → all done
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 200

    async def test_status_becomes_completed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/complete")).json()
        assert body["status"] == "completed"

    async def test_sets_completed_at(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2
        await db_session.commit()
        await auth_client.post(f"/api/projects/{project.id}/complete")
        await db_session.refresh(project)
        assert project.completed_at is not None

    async def test_fails_if_not_at_last_pick_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        # seq.current_pick=1, section_total=2 → agg_current(1) < total_picks(2)
        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 400

    async def test_fails_if_not_on_last_item_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        project.current_item = 1
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # all sequence picks done
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 400

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

    async def test_force_completes_mid_progress(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        # current_pick=1, tracker incomplete — force should succeed
        resp = await auth_client.post(f"/api/projects/{project.id}/complete?force=true")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    async def test_force_preserves_pick_data(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/complete?force=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_picks"] == 2  # weft=2 * repeats=1
        assert body["current_pick"] == 1  # unchanged

    async def test_force_false_still_blocks_incomplete(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/complete?force=false")
        assert resp.status_code == 400


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
# TestAdvanceItem
# ---------------------------------------------------------------------------


class TestAdvanceItem:
    async def test_increments_item_and_resets_pick(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        project.current_item = 1
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total (weft=2, repeats=1) → all done
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/advance-item")).json()
        assert body["current_item"] == 2
        assert body["current_pick"] == 0

    async def test_response_includes_num_items(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        project.current_item = 1
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total → all done
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/advance-item")).json()
        assert body["num_items"] == 3

    async def test_fails_if_not_at_item_end_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        project.current_item = 1
        # current_pick still at 1, not at item end
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/advance-item")
        assert resp.status_code == 400

    async def test_fails_if_on_last_item_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        project.current_item = 3
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total → sequence done, but already on last item
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/advance-item")
        assert resp.status_code == 400

    async def test_single_item_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total → sequence done; num_items=1, current_item=1 → last item
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/advance-item")
        assert resp.status_code == 400

    async def test_inactive_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/advance-item")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/advance-item")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/advance-item")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestJumpItem
# ---------------------------------------------------------------------------


class TestJumpItem:
    async def test_sets_item(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 5
        project.current_item = 3
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/jump-item", json={"item": 2})).json()
        assert body["current_item"] == 2
        assert body["current_pick"] == 1  # seq entry current_pick unchanged by jump-item

    async def test_clamps_above_num_items(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/jump-item", json={"item": 99})).json()
        assert body["current_item"] == 3

    async def test_clamps_below_one(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.num_items = 3
        await db_session.commit()
        body = (await auth_client.post(f"/api/projects/{project.id}/jump-item", json={"item": 0})).json()
        assert body["current_item"] == 1

    async def test_inactive_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "completed"
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/jump-item", json={"item": 1})
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/jump-item", json={"item": 1})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.post(f"/api/projects/{project.id}/jump-item", json={"item": 1})
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
            name="Lift project",
            project_type="lift",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        seq = ProjectDraft(project_id=project.id, draft_id=draft.id, position=1, repeats=1, current_pick=1)
        db_session.add(seq)
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
        loom, _ = await _insert_loom(db_session, test_user, loom_type="rigid_heddle")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom.id)),
        )
        assert resp.status_code == 422

    async def test_dobby_loom_blocks_create(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        loom, _ = await _insert_loom(db_session, test_user, loom_type="dobby")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom.id)),
        )
        assert resp.status_code == 422

    async def test_floor_loom_allowed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        loom, _ = await _insert_loom(db_session, test_user, loom_type="floor_loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom.id)),
        )
        assert resp.status_code == 201

    async def test_table_loom_allowed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        loom, _ = await _insert_loom(db_session, test_user, loom_type="table_loom")
        resp = await auth_client.post(
            "/api/projects",
            json=_base_payload(loom_id=str(loom.id)),
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


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/drawdown
# ---------------------------------------------------------------------------

_TILE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG header


async def _insert_project_with_wif(
    db_session: AsyncSession,
    owner: User,
    *,
    warp_threads: int = 4,
    weft_threads: int = 4,
) -> tuple[Draft, "Project"]:
    import app.services.storage as storage

    draft_id = uuid.uuid4()
    wif_key = storage.save_wif(draft_id, "test.wif", _WIF_RENDERABLE)
    draft = Draft(
        id=draft_id,
        owner_id=owner.id,
        name="Tile Test Draft",
        wif_filename="test.wif",
        wif_path=wif_key,
        has_treadling=True,
        has_liftplan=False,
        num_shafts=4,
        num_treadles=4,
        warp_threads=warp_threads,
        weft_threads=weft_threads,
    )
    db_session.add(draft)
    await db_session.flush()

    project = Project(
        owner_id=owner.id,
        name="Tile Test Project",
        project_type="treadle",
        status="active",
    )
    db_session.add(project)
    await db_session.flush()
    seq = ProjectDraft(project_id=project.id, draft_id=draft.id, position=1, repeats=1, current_pick=1)
    db_session.add(seq)
    await db_session.commit()
    return draft, project


class TestProjectDrawdown:
    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4")
        assert resp.status_code == 401

    async def test_returns_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/drawdown?start_row=0&row_count=4")
        assert resp.status_code == 404

    async def test_renders_and_returns_png_on_cache_miss(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == b"\x89PNG"

    async def test_returns_dimension_headers(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4")
        assert resp.status_code == 200
        assert resp.headers.get("X-Total-Rows") == "4"
        assert resp.headers.get("X-Total-Cols") == "4"
        assert resp.headers.get("X-Start-Row") == "0"
        assert resp.headers.get("X-Pixels-Per-Row") is not None

    async def test_cache_miss_no_store_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4")
        assert resp.headers.get("Cache-Control") == "no-store"

    async def test_cache_hit_returns_stored_bytes(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        settings = get_settings()
        draft, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4)
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // 4, DRAWDOWN_SCALE)
        storage.save_project_tile(project.id, expected_scale, 0, _TILE_PNG)

        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count={tile_row_count}")
        assert resp.status_code == 200
        assert resp.content == _TILE_PNG

    async def test_cache_hit_immutable_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        settings = get_settings()
        draft, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4)
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // 4, DRAWDOWN_SCALE)
        storage.save_project_tile(project.id, expected_scale, 0, _TILE_PNG)

        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count={tile_row_count}")
        assert "immutable" in (resp.headers.get("Cache-Control") or "")

    async def test_cache_miss_triggers_prerender_task(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, _mock_tile_task
    ):
        from app.config import get_settings

        settings = get_settings()
        _, project = await _insert_project_with_wif(db_session, test_user)
        tile_row_count = settings.tile_row_count

        await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count={tile_row_count}")
        _mock_tile_task.apply_async.assert_called_once_with(args=[str(project.id)])

    async def test_cache_miss_skips_task_when_t0_exists(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, _mock_tile_task
    ):
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        settings = get_settings()
        draft, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4)
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // 4, DRAWDOWN_SCALE)

        storage.save_project_tile(project.id, expected_scale, 0, _TILE_PNG)

        resp = await auth_client.get(
            f"/api/projects/{project.id}/drawdown?start_row={tile_row_count}&row_count={tile_row_count}"
        )
        assert resp.status_code == 200
        _mock_tile_task.apply_async.assert_not_called()

    # --- column slicing ---

    async def test_col_slice_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(
            f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4&start_col=0&col_count=2"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_col_slice_returns_start_col_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(
            f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4&start_col=1&col_count=2"
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Start-Col") == "1"
        assert resp.headers.get("X-Col-Count") is not None

    async def test_col_slice_narrower_than_full_width(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        import io as _io

        from PIL import Image as PILImage

        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4)
        resp_full = await auth_client.get(f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4")
        resp_col = await auth_client.get(
            f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4&start_col=0&col_count=2"
        )
        assert resp_full.status_code == 200
        assert resp_col.status_code == 200
        img_full = PILImage.open(_io.BytesIO(resp_full.content))
        img_col = PILImage.open(_io.BytesIO(resp_col.content))
        assert img_col.width < img_full.width

    async def test_col_slice_invalid_start_col_returns_422(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(
            f"/api/projects/{project.id}/drawdown?start_row=0&row_count=4&start_col=-1&col_count=2"
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TestWeaveSessions
# ---------------------------------------------------------------------------


class TestWeaveSessions:
    async def test_first_step_opens_session(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        from sqlalchemy import select

        from app.models.project import WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        session = await db_session.scalar(select(WeaveSession).where(WeaveSession.project_id == project.id))
        assert session is not None
        assert session.ended_at is None

    async def test_second_step_within_timeout_keeps_session(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from sqlalchemy import select

        from app.models.project import ProjectStep, WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 0  # reset so 2 advances are possible (section_total=2)
        await db_session.commit()

        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})

        sessions = (await db_session.scalars(select(WeaveSession).where(WeaveSession.project_id == project.id))).all()
        assert len(sessions) == 1
        assert sessions[0].ended_at is None

        # Second step should have a dwell_ms set
        steps = (
            await db_session.scalars(
                select(ProjectStep).where(ProjectStep.project_id == project.id).order_by(ProjectStep.created_at)
            )
        ).all()
        assert steps[0].dwell_ms is None  # first step has no previous
        assert steps[1].dwell_ms is not None

    async def test_step_after_idle_timeout_closes_old_and_opens_new_session(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from sqlalchemy import select

        from app.models.project import ProjectStep, WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)

        # Insert a step with a timestamp older than the idle timeout (30 min default)
        old_step = ProjectStep(
            project_id=project.id,
            event_type="advance",
            from_pick=0,
            to_pick=1,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(old_step)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 1  # 1 pick still available (section_total=2)
        # Manually insert an open session
        old_session = WeaveSession(
            project_id=project.id,
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(old_session)
        await db_session.commit()

        # Trigger a new step — gap is > 30 min, so should close old session and open new
        resp = await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        assert resp.status_code == 200

        await db_session.refresh(old_session)
        assert old_session.ended_at is not None

        sessions = (await db_session.scalars(select(WeaveSession).where(WeaveSession.project_id == project.id))).all()
        assert len(sessions) == 2
        open_sessions = [s for s in sessions if s.ended_at is None]
        assert len(open_sessions) == 1

    async def test_dwell_ms_capped_at_idle_timeout(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from sqlalchemy import select

        from app.models.project import ProjectStep, WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)

        old_step = ProjectStep(
            project_id=project.id,
            event_type="advance",
            from_pick=0,
            to_pick=1,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db_session.add(old_step)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 1  # 1 pick still available (section_total=2)
        db_session.add(
            WeaveSession(
                project_id=project.id,
                started_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        await db_session.commit()

        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})

        new_step = await db_session.scalar(
            select(ProjectStep)
            .where(ProjectStep.project_id == project.id)
            .order_by(ProjectStep.created_at.desc())
            .limit(1)
        )
        assert new_step is not None
        idle_timeout_ms = test_user.idle_timeout_minutes * 60 * 1_000
        assert new_step.dwell_ms == idle_timeout_ms

    async def test_complete_closes_open_session(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):

        from app.models.project import WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 2  # section_total → complete
        await db_session.commit()

        open_session = WeaveSession(project_id=project.id, started_at=datetime.now(timezone.utc))
        db_session.add(open_session)
        await db_session.commit()

        resp = await auth_client.post(f"/api/projects/{project.id}/complete")
        assert resp.status_code == 200

        await db_session.refresh(open_session)
        assert open_session.ended_at is not None

    async def test_abandon_closes_open_session(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):

        from app.models.project import WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)

        open_session = WeaveSession(project_id=project.id, started_at=datetime.now(timezone.utc))
        db_session.add(open_session)
        await db_session.commit()

        resp = await auth_client.post(f"/api/projects/{project.id}/abandon")
        assert resp.status_code == 200

        await db_session.refresh(open_session)
        assert open_session.ended_at is not None


# ---------------------------------------------------------------------------
# TestProjectMetrics
# ---------------------------------------------------------------------------


class TestProjectMetrics:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}/metrics")
        assert resp.status_code == 200

    async def test_empty_metrics_for_new_project(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["total_sessions"] == 0
        assert body["total_advance_steps"] == 0
        assert body["total_worked_picks"] == 0

    async def test_counts_advance_and_reverse_steps(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        seq = await _get_seq_entry(db_session, project)
        seq.current_pick = 0  # start from 0 so 2 advances are available (section_total=2)
        await db_session.commit()
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "advance"})
        await auth_client.post(f"/api/projects/{project.id}/step", json={"direction": "reverse"})
        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["total_advance_steps"] == 2
        assert body["total_reverse_steps"] == 1

    async def test_worked_picks_excludes_fast_steps(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):

        from app.models.project import ProjectStep

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)

        # Insert two steps: first with dwell > threshold, second with dwell < threshold
        step1 = ProjectStep(
            project_id=project.id,
            event_type="advance",
            from_pick=1,
            to_pick=2,
            dwell_ms=5_000,  # 5s — worked
        )
        step2 = ProjectStep(
            project_id=project.id,
            event_type="advance",
            from_pick=2,
            to_pick=3,
            dwell_ms=500,  # 0.5s — navigation
        )
        db_session.add_all([step1, step2])
        await db_session.commit()

        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["total_worked_picks"] == 1

    async def test_current_session_started_at_set_when_open(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from app.models.project import WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        db_session.add(WeaveSession(project_id=project.id, started_at=datetime.now(timezone.utc)))
        await db_session.commit()

        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["current_session_started_at"] is not None

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/metrics")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/metrics")
        assert resp.status_code == 401

    async def test_avg_pick_dwell_ms_none_when_no_worked_picks(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["avg_pick_dwell_ms"] is None

    async def test_avg_pick_dwell_ms_computed_correctly(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from app.models.project import ProjectStep

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        db_session.add_all(
            [
                ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, dwell_ms=6_000),
                ProjectStep(project_id=project.id, event_type="advance", from_pick=2, to_pick=3, dwell_ms=10_000),
            ]
        )
        await db_session.commit()

        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["avg_pick_dwell_ms"] == 8_000

    async def test_avg_pick_dwell_ms_excludes_sub_threshold_and_reverse(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        from app.models.project import ProjectStep

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        db_session.add_all(
            [
                ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, dwell_ms=8_000),
                ProjectStep(
                    project_id=project.id, event_type="advance", from_pick=2, to_pick=3, dwell_ms=500
                ),  # navigation
                ProjectStep(
                    project_id=project.id, event_type="reverse", from_pick=3, to_pick=2, dwell_ms=12_000
                ),  # reverse
            ]
        )
        await db_session.commit()

        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["avg_pick_dwell_ms"] == 8_000

    async def test_session_step_count(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        from app.models.project import ProjectStep, WeaveSession

        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)

        t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
        t1 = datetime.now(timezone.utc) - timedelta(minutes=5)
        t2 = datetime.now(timezone.utc) - timedelta(minutes=2)

        sess = WeaveSession(project_id=project.id, started_at=t0, ended_at=t1)
        db_session.add(sess)
        await db_session.flush()

        # 3 steps inside the session window, 1 after
        db_session.add_all(
            [
                ProjectStep(
                    project_id=project.id,
                    event_type="advance",
                    from_pick=1,
                    to_pick=2,
                    created_at=t0 + timedelta(seconds=10),
                ),
                ProjectStep(
                    project_id=project.id,
                    event_type="advance",
                    from_pick=2,
                    to_pick=3,
                    created_at=t0 + timedelta(seconds=20),
                ),
                ProjectStep(
                    project_id=project.id,
                    event_type="reverse",
                    from_pick=3,
                    to_pick=2,
                    created_at=t0 + timedelta(seconds=30),
                ),
                ProjectStep(
                    project_id=project.id, event_type="advance", from_pick=2, to_pick=3, created_at=t2
                ),  # outside session
            ]
        )
        await db_session.commit()

        body = (await auth_client.get(f"/api/projects/{project.id}/metrics")).json()
        assert body["sessions"][0]["step_count"] == 3


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/drawdown/svg
# ---------------------------------------------------------------------------


class TestProjectDrawdownSvg:
    async def test_returns_200_with_svg_content_type(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]

    async def test_response_body_is_valid_svg(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg")
        assert b"<svg" in resp.content
        assert b"</svg>" in resp.content

    async def test_response_contains_symbol_defs_and_float_borders(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg")
        # Symbol-dedup: O(weft) DOM elements.
        assert b"<symbol" in resp.content
        assert b"<use" in resp.content
        # Float-boundary borders: single <path> with outline of each visible float.
        assert b'stroke="#7f7f7f"' in resp.content

    async def test_returns_dimension_headers(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg")
        assert resp.headers.get("X-Total-Rows") == "4"
        assert resp.headers.get("X-Total-Cols") == "4"
        assert resp.headers.get("X-Pixels-Per-Row") == "20"

    async def test_cell_px_param_scales_output(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg?cell_px=10")
        assert resp.status_code == 200
        assert resp.headers.get("X-Pixels-Per-Row") == "10"
        assert b'width="40"' in resp.content  # 4 warps × 10 px

    async def test_returns_404_when_wif_missing_from_storage(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft_id = uuid.uuid4()
        draft = Draft(
            id=draft_id,
            owner_id=test_user.id,
            name="Missing WIF Draft",
            wif_filename="missing.wif",
            wif_path="drafts/missing/original.wif",  # path not in storage
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            name="No WIF Project",
            project_type="treadle",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(ProjectDraft(project_id=project.id, draft_id=draft.id, position=1, repeats=1, current_pick=1))
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/svg")
        assert resp.status_code == 404

    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await client.get(f"/api/projects/{project.id}/drawdown/svg")
        assert resp.status_code == 401

    async def test_returns_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/drawdown/svg")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/drawdown/data
# ---------------------------------------------------------------------------


class TestProjectDrawdownData:
    async def test_returns_200_with_json_content_type(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    async def test_response_body_has_required_keys(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data")
        body = resp.json()
        assert "cell_px" in body
        assert "warp_count" in body
        assert "weft_count" in body
        assert "floats" in body
        assert isinstance(body["floats"], list)

    async def test_each_float_is_5_element_list_with_color(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data")
        floats = resp.json()["floats"]
        assert len(floats) > 0
        for f in floats:
            assert isinstance(f, list)
            assert len(f) == 5
            x, y, w, h, color = f
            assert isinstance(x, int)
            assert isinstance(y, int)
            assert isinstance(w, int) and w > 0
            assert isinstance(h, int) and h > 0
            assert isinstance(color, str) and color.startswith("#")

    async def test_returns_dimension_headers(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data")
        assert resp.headers.get("X-Total-Rows") == "4"
        assert resp.headers.get("X-Total-Cols") == "4"
        assert resp.headers.get("X-Pixels-Per-Row") == "20"

    async def test_cell_px_param_scales_output(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data?cell_px=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cell_px"] == 10
        assert resp.headers.get("X-Pixels-Per-Row") == "10"
        # all float dimensions must be multiples of cell_px=10
        for x, y, w, h, _ in body["floats"]:
            assert x % 10 == 0
            assert y % 10 == 0
            assert w % 10 == 0
            assert h % 10 == 0

    async def test_float_coords_match_weft_count_and_cell_px(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user, warp_threads=4, weft_threads=4)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data?cell_px=20")
        body = resp.json()
        total_h = body["weft_count"] * body["cell_px"]  # 4 * 20 = 80
        total_w = body["warp_count"] * body["cell_px"]  # 4 * 20 = 80
        for x, y, w, h, _ in body["floats"]:
            assert 0 <= x < total_w
            assert 0 <= y < total_h
            assert x + w <= total_w
            assert y + h <= total_h

    async def test_returns_404_when_wif_missing_from_storage(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft_id = uuid.uuid4()
        draft = Draft(
            id=draft_id,
            owner_id=test_user.id,
            name="Missing WIF Draft",
            wif_filename="missing.wif",
            wif_path="drafts/missing/original.wif",
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            name="No WIF Project",
            project_type="treadle",
            status="active",
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(ProjectDraft(project_id=project.id, draft_id=draft.id, position=1, repeats=1, current_pick=1))
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/data")
        assert resp.status_code == 404

    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await client.get(f"/api/projects/{project.id}/drawdown/data")
        assert resp.status_code == 401

    async def test_returns_404_for_unknown_project(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/drawdown/data")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestStartProject
# ---------------------------------------------------------------------------


class TestStartProject:
    async def test_created_transitions_to_active(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, loom, "created")
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_returns_400_when_no_sequence(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        loom, _ = await _insert_loom(db_session, test_user)
        project = Project(owner_id=test_user.id, name="Empty seq", loom_id=loom.id, status="created")
        db_session.add(project)
        await db_session.commit()
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 400

    async def test_returns_400_when_no_loom(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "created")
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 400

    async def test_idempotent_when_already_active(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    async def test_completed_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "completed")
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 400

    async def test_abandoned_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "abandoned")
        resp = await auth_client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project_with_status(db_session, test_user, draft, None, "created")
        resp = await client.post(f"/api/projects/{project.id}/start")
        assert resp.status_code == 401

    async def test_unknown_project_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/start")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestSetColorReplacements
# ---------------------------------------------------------------------------


class TestSetColorReplacements:
    async def test_stores_replacements(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = {"color_replacements": {"#ff0000": "#0000ff"}}
        resp = await auth_client.patch(f"/api/projects/{project.id}/color-replacements", json=body)
        assert resp.status_code == 200
        assert resp.json()["color_replacements"] == {"#ff0000": "#0000ff"}

    async def test_replaces_existing_map(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.color_replacements = {"#aaaaaa": "#bbbbbb"}
        await db_session.commit()
        body = {"color_replacements": {"#111111": "#222222"}}
        resp = await auth_client.patch(f"/api/projects/{project.id}/color-replacements", json=body)
        assert resp.json()["color_replacements"] == {"#111111": "#222222"}

    async def test_empty_map_clears_replacements(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.color_replacements = {"#ff0000": "#0000ff"}
        await db_session.commit()
        body = {"color_replacements": {}}
        resp = await auth_client.patch(f"/api/projects/{project.id}/color-replacements", json=body)
        assert resp.status_code == 200
        assert resp.json()["color_replacements"] is None

    async def test_invalid_hex_returns_422(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = {"color_replacements": {"notahex": "#0000ff"}}
        resp = await auth_client.patch(f"/api/projects/{project.id}/color-replacements", json=body)
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = {"color_replacements": {"#ff0000": "#0000ff"}}
        resp = await client.patch(f"/api/projects/{project.id}/color-replacements", json=body)
        assert resp.status_code == 401

    async def test_unknown_project_returns_404(self, auth_client: AsyncClient):
        body = {"color_replacements": {"#ff0000": "#0000ff"}}
        resp = await auth_client.patch(f"/api/projects/{uuid.uuid4()}/color-replacements", json=body)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestUpdateWarpSetup — PATCH /{project_id}/warp-setup
# ---------------------------------------------------------------------------


class TestUpdateWarpSetup:
    async def test_updates_num_items_when_created(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.status = "created"
        await db_session.commit()
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={"num_items": 3})
        assert resp.status_code == 200
        assert resp.json()["num_items"] == 3

    async def test_num_items_rejected_when_active(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={"num_items": 3})
        assert resp.status_code == 400

    async def test_updates_finished_length(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(
            f"/api/projects/{project.id}/warp-setup", json={"finished_length_per_item": 100.0}
        )
        assert resp.status_code == 200
        assert float(resp.json()["finished_length_per_item"]) == 100.0

    async def test_updates_waste_between_items(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={"waste_between_items": 5.0})
        assert resp.status_code == 200

    async def test_updates_warp_waste_allowance(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={"warp_waste_allowance": 20.0})
        assert resp.status_code == 200

    async def test_updates_length_unit(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={"length_unit": "in"})
        assert resp.status_code == 200

    async def test_empty_body_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/warp-setup", json={})
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.patch(f"/api/projects/{project.id}/warp-setup", json={"num_items": 2})
        assert resp.status_code == 401

    async def test_unknown_project_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/projects/{uuid.uuid4()}/warp-setup", json={"num_items": 2})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestSetReed — PATCH /{project_id}/reed
# ---------------------------------------------------------------------------


class TestSetReed:
    async def test_sets_reed_dents(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/reed", json={"reed_dents_per_inch": 12.0})
        assert resp.status_code == 200
        assert resp.json()["reed_dents_per_inch"] == 12.0

    async def test_clears_reed(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/reed", json={"reed_dents_per_inch": None})
        assert resp.status_code == 200
        assert resp.json()["reed_dents_per_inch"] is None

    async def test_negative_dents_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/reed", json={"reed_dents_per_inch": -1.0})
        assert resp.status_code == 400

    async def test_zero_dents_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/reed", json={"reed_dents_per_inch": 0.0})
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.patch(f"/api/projects/{project.id}/reed", json={"reed_dents_per_inch": 12.0})
        assert resp.status_code == 401

    async def test_unknown_project_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/projects/{uuid.uuid4()}/reed", json={"reed_dents_per_inch": 12.0})
        assert resp.status_code == 404

    async def test_drawdown_preview_cached_404_when_missing(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.drawdown_preview_path = None
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown_preview")
        assert resp.status_code == 404

    async def test_drawdown_svg_cached_404_when_missing(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.drawdown_svg_path = None
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown_svg")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestShareProject — PATCH/DELETE /{project_id}/share
# ---------------------------------------------------------------------------


class TestShareProject:
    async def test_share_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
        assert resp.status_code == 200

    async def test_share_sets_slug(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})).json()
        assert body["share_slug"] is not None
        assert body["share_visibility"] == "link"

    async def test_share_sets_expiry(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (
            await auth_client.patch(
                f"/api/projects/{project.id}/share",
                json={"visibility": "link", "expires_at": "2099-01-01T00:00:00Z"},
            )
        ).json()
        assert body["share_expires_at"] is not None

    async def test_second_share_reuses_slug(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body1 = (await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})).json()
        body2 = (await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})).json()
        assert body1["share_slug"] == body2["share_slug"]

    async def test_share_invalid_visibility_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "public"})
        assert resp.status_code == 400

    async def test_share_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/projects/{uuid.uuid4()}/share", json={"visibility": "link"})
        assert resp.status_code == 404

    async def test_share_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
        assert resp.status_code == 401

    async def test_revoke_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
        resp = await auth_client.delete(f"/api/projects/{project.id}/share")
        assert resp.status_code == 204

    async def test_revoke_clears_slug(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
        await auth_client.delete(f"/api/projects/{project.id}/share")
        await db_session.refresh(project)
        assert project.share_slug is None
        assert project.share_visibility == "private"

    async def test_revoke_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/projects/{uuid.uuid4()}/share")
        assert resp.status_code == 404

    async def test_revoke_unauthenticated_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.delete(f"/api/projects/{project.id}/share")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestGetSharedProject — GET /api/share/projects/{slug}
# ---------------------------------------------------------------------------


async def _share_project(db_session: AsyncSession, project: "Project", slug: str = "test-slug-abc") -> None:
    project.share_slug = slug
    project.share_visibility = "link"
    await db_session.commit()


class TestGetSharedProject:
    async def test_returns_200_for_valid_slug(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await _share_project(db_session, project, "my-slug-abc1")
        resp = await client.get("/api/share/projects/my-slug-abc1")
        assert resp.status_code == 200

    async def test_returns_project_fields(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await _share_project(db_session, project, "my-slug-abc2")
        body = (await client.get("/api/share/projects/my-slug-abc2")).json()
        assert body["project_name"] == project.name
        assert body["share_visibility"] == "link"
        assert "has_drawdown_preview" in body

    async def test_private_slug_returns_404(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.share_slug = "private-slug"
        project.share_visibility = "private"
        await db_session.commit()
        resp = await client.get("/api/share/projects/private-slug")
        assert resp.status_code == 404

    async def test_unknown_slug_returns_404(self, client: AsyncClient):
        resp = await client.get("/api/share/projects/does-not-exist")
        assert resp.status_code == 404

    async def test_expired_slug_returns_410(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.share_slug = "expired-slug"
        project.share_visibility = "link"
        project.share_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await db_session.commit()
        resp = await client.get("/api/share/projects/expired-slug")
        assert resp.status_code == 410

    async def test_no_auth_required(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await _share_project(db_session, project, "my-slug-abc3")
        resp = await client.get("/api/share/projects/my-slug-abc3")
        assert resp.status_code == 200


class TestGetSharedProjectPreview:
    async def test_returns_404_when_no_preview(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await _share_project(db_session, project, "prev-slug1")
        resp = await client.get("/api/share/projects/prev-slug1/preview")
        assert resp.status_code == 404

    async def test_returns_404_for_private_project(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.share_slug = "prev-priv-slug"
        project.share_visibility = "private"
        await db_session.commit()
        resp = await client.get("/api/share/projects/prev-priv-slug/preview")
        assert resp.status_code == 404

    async def test_returns_410_for_expired_link(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.share_slug = "prev-exp-slug"
        project.share_visibility = "link"
        project.share_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await db_session.commit()
        resp = await client.get("/api/share/projects/prev-exp-slug/preview")
        assert resp.status_code == 410

    async def test_returns_png_when_preview_exists(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        preview_path = f"project-previews/{project.id}/preview.png"
        mock_storage[preview_path] = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        project.drawdown_preview_path = preview_path
        await _share_project(db_session, project, "prev-ok-slug")
        resp = await client.get("/api/share/projects/prev-ok-slug/preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"


class TestGetSharedProjectSvg:
    async def test_returns_404_when_no_svg(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        await _share_project(db_session, project, "svg-slug1")
        resp = await client.get("/api/share/projects/svg-slug1/svg")
        assert resp.status_code == 404

    async def test_returns_svg_when_exists(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        svg_path = f"project-svgs/{project.id}/drawdown.svg"
        mock_storage[svg_path] = b"<svg></svg>"
        project.drawdown_svg_path = svg_path
        await _share_project(db_session, project, "svg-ok-slug")
        resp = await client.get("/api/share/projects/svg-ok-slug/svg")
        assert resp.status_code == 200
        assert "svg" in resp.headers["content-type"]

    async def test_returns_410_for_expired(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        project.share_slug = "svg-exp-slug"
        project.share_visibility = "link"
        project.share_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        await db_session.commit()
        resp = await client.get("/api/share/projects/svg-exp-slug/svg")
        assert resp.status_code == 410


# ---------------------------------------------------------------------------
# TestWarpingPlan — GET /{project_id}/warping-plan
# ---------------------------------------------------------------------------


class TestWarpingPlan:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}/warping-plan")
        assert resp.status_code == 200

    async def test_returns_required_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/warping-plan")).json()
        assert "project_id" in body
        assert "draft_name" in body
        assert "project_type" in body
        assert "warp_color_summary" in body
        assert "weft_color_summary" in body

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/warping-plan")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/warping-plan")
        assert resp.status_code == 401

    async def test_has_threading_when_wif_has_it(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        draft.has_threading = True
        await db_session.commit()
        project = await _insert_active_project(db_session, test_user, draft, None)
        body = (await auth_client.get(f"/api/projects/{project.id}/warping-plan")).json()
        assert body["has_threading"] is True


# ---------------------------------------------------------------------------
# TestDrawdownPreviewEndpoint — GET /{project_id}/drawdown/preview
# ---------------------------------------------------------------------------


class TestDrawdownPreviewEndpoint:
    async def test_returns_png(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_returns_404_when_wif_missing(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        draft.wif_path = "drafts/nonexistent.wif"
        await db_session.commit()
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/preview")
        assert resp.status_code == 404

    async def test_invalid_color_replacements_json_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown/preview?color_replacements=not-json")
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        _, project = await _insert_project_with_wif(db_session, test_user)
        resp = await client.get(f"/api/projects/{project.id}/drawdown/preview")
        assert resp.status_code == 401

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/projects/{uuid.uuid4()}/drawdown/preview")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestCachedDrawdownPreviewAndSvg
# ---------------------------------------------------------------------------


class TestCachedDrawdownPreview:
    async def test_returns_png_when_present(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        preview_path = f"project-previews/{project.id}/preview.png"
        mock_storage[preview_path] = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        project.drawdown_preview_path = preview_path
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown_preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/drawdown_preview")
        assert resp.status_code == 401


class TestCachedDrawdownSvg:
    async def test_returns_svg_when_present(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        svg_path = f"project-svgs/{project.id}/drawdown.svg"
        mock_storage[svg_path] = b"<svg><rect/></svg>"
        project.drawdown_svg_path = svg_path
        await db_session.commit()
        resp = await auth_client.get(f"/api/projects/{project.id}/drawdown_svg")
        assert resp.status_code == 200
        assert "svg" in resp.headers["content-type"]

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_active_project(db_session, test_user, draft, None)
        resp = await client.get(f"/api/projects/{project.id}/drawdown_svg")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestSlugifyHelper
# ---------------------------------------------------------------------------


class TestSlugifyHelper:
    def test_basic_slugify(self):
        from app.routers.projects import _slugify

        assert _slugify("My Draft Name") == "my-draft-name"

    def test_strips_special_chars(self):
        from app.routers.projects import _slugify

        assert _slugify("Hello! World?") == "hello-world"

    def test_empty_input_returns_project(self):
        from app.routers.projects import _slugify

        assert _slugify("   ") == "project"

    def test_truncates_long_name(self):
        from app.routers.projects import _slugify

        long_name = "a" * 100
        result = _slugify(long_name)
        assert len(result) <= 48


# ---------------------------------------------------------------------------
# TestComputeColorRuns
# ---------------------------------------------------------------------------


class TestComputeColorRuns:
    def test_empty_returns_empty(self):
        from app.routers.projects import _compute_color_runs

        assert _compute_color_runs([]) == []

    def test_single_entry(self):
        from app.routers.projects import _compute_color_runs

        entries = [{"color": "#ff0000", "color_name": "Red", "end": 1}]
        runs = _compute_color_runs(entries)
        assert len(runs) == 1
        assert runs[0].color == "#ff0000"
        assert runs[0].count == 1

    def test_consecutive_same_color_merged(self):
        from app.routers.projects import _compute_color_runs

        entries = [
            {"color": "#ff0000", "color_name": "Red", "end": 1},
            {"color": "#ff0000", "color_name": "Red", "end": 2},
            {"color": "#ff0000", "color_name": "Red", "end": 3},
        ]
        runs = _compute_color_runs(entries)
        assert len(runs) == 1
        assert runs[0].count == 3

    def test_color_change_creates_new_run(self):
        from app.routers.projects import _compute_color_runs

        entries = [
            {"color": "#ff0000", "color_name": "Red", "end": 1},
            {"color": "#0000ff", "color_name": "Blue", "end": 2},
        ]
        runs = _compute_color_runs(entries)
        assert len(runs) == 2
        assert runs[0].color == "#ff0000"
        assert runs[1].color == "#0000ff"
