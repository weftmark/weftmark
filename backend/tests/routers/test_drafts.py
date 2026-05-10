"""Tests for the /api/drafts router."""

import io
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.draft import Draft
from app.models.user import User
from app.services import rendering


@pytest.fixture(autouse=True)
def _mock_preview_task(monkeypatch):
    """Prevent generate_drawdown_preview.delay() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.drafts.generate_drawdown_preview", mock)
    return mock


@pytest.fixture(autouse=True)
def _mock_tile_task(monkeypatch):
    """Prevent prerender_drawdown_tiles.apply_async() from connecting to Celery in tests."""
    mock = MagicMock()
    monkeypatch.setattr("app.routers.drafts.prerender_drawdown_tiles", mock)
    return mock


# ---------------------------------------------------------------------------
# Unit tests for _has_wif_header
# ---------------------------------------------------------------------------


class TestHasWifHeader:
    def setup_method(self):
        from app.routers.drafts import _has_wif_header

        self.check = _has_wif_header

    def test_plain_wif_header(self):
        assert self.check(b"[WIF]\nVersion=1.1\n") is True

    def test_wif_header_case_insensitive(self):
        assert self.check(b"[wif]\nVersion=1.1\n") is True

    def test_single_comment_then_wif(self):
        assert self.check(b"; exported by Tempo Weave\r\n[WIF]\r\nVersion=1.1\r\n") is True

    def test_multiple_comments_then_wif(self):
        assert self.check(b"; line 1\r\n; line 2\r\n[WIF]\r\n") is True

    def test_non_wif_content(self):
        assert self.check(b"not a wif file") is False

    def test_jpeg_magic(self):
        assert self.check(b"\xff\xd8\xff\xe0" + b"\x00" * 100) is False

    def test_empty_bytes(self):
        assert self.check(b"") is False

    def test_only_comments_no_wif(self):
        assert self.check(b"; just a comment\n; another\n") is False

    def test_wif_after_non_comment_line_rejected(self):
        assert self.check(b"random line\n[WIF]\n") is False

    def test_whitespace_before_wif(self):
        assert self.check(b"\r\n\n[WIF]\n") is True


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


async def _insert_draft(
    db_session: AsyncSession,
    owner: User,
    *,
    wif_path: str = "",
    weft_threads: int = 4,
) -> Draft:
    draft = Draft(
        owner_id=owner.id,
        name="Test Draft",
        wif_filename="test.wif",
        wif_path=wif_path,
        has_treadling=True,
        num_shafts=4,
        num_treadles=4,
        weft_threads=weft_threads,
    )
    db_session.add(draft)
    await db_session.commit()
    return draft


# ---------------------------------------------------------------------------
# GET /api/drafts
# ---------------------------------------------------------------------------


class TestListDrafts:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/drafts")
        assert resp.status_code == 200

    async def test_empty_list_when_no_drafts(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/drafts")
        assert resp.json() == []

    async def test_returns_created_draft(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        resp = await auth_client.get("/api/drafts")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Draft"

    async def test_does_not_return_deleted_draft(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        draft.soft_delete()
        await db_session.commit()
        resp = await auth_client.get("/api/drafts")
        assert resp.json() == []

    async def test_does_not_return_other_users_drafts(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        await _insert_draft(db_session, admin_user, wif_path="d/other.wif")
        resp = await auth_client.get("/api/drafts")
        assert resp.json() == []

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/drafts")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/drafts/{draft_id}
# ---------------------------------------------------------------------------


class TestGetDraft:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}")
        assert resp.status_code == 200

    async def test_returns_draft_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        data = (await auth_client.get(f"/api/drafts/{draft.id}")).json()
        assert data["name"] == "Test Draft"
        assert data["wif_filename"] == "test.wif"
        assert "has_preview" in data

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/drafts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_draft_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = await _insert_draft(db_session, admin_user, wif_path="d/other.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get(f"/api/drafts/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/drafts/{draft_id}
# ---------------------------------------------------------------------------


class TestDeleteDraft:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        resp = await auth_client.delete(f"/api/drafts/{draft.id}")
        assert resp.status_code == 204

    async def test_draft_not_in_list_after_delete(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        await auth_client.delete(f"/api/drafts/{draft.id}")
        resp = await auth_client.get("/api/drafts")
        assert resp.json() == []

    async def test_get_after_delete_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        await auth_client.delete(f"/api/drafts/{draft.id}")
        resp = await auth_client.get(f"/api/drafts/{draft.id}")
        assert resp.status_code == 404

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/drafts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_draft_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = await _insert_draft(db_session, admin_user, wif_path="d/other.wif")
        resp = await auth_client.delete(f"/api/drafts/{draft.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.delete(f"/api/drafts/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_soft_deletes_in_db(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        await auth_client.delete(f"/api/drafts/{draft.id}")
        await db_session.refresh(draft)
        assert draft.deleted_at is not None


# ---------------------------------------------------------------------------
# GET /{draft_id}/drawdown
# ---------------------------------------------------------------------------


class TestGetDrawdown:
    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="x.wif")
        resp = await client.get(f"/api/drafts/{draft.id}/drawdown")
        assert resp.status_code == 401

    async def test_returns_404_for_unknown_draft(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/drafts/{uuid.uuid4()}/drawdown")
        assert resp.status_code == 404

    async def test_returns_404_for_other_users_draft(
        self,
        db_session: AsyncSession,
        auth_client: AsyncClient,
        admin_user: User,
    ):
        other_draft = await _insert_draft(db_session, admin_user, wif_path="x.wif")
        resp = await auth_client.get(f"/api/drafts/{other_draft.id}/drawdown")
        assert resp.status_code == 404

    async def test_returns_404_when_no_wif_path(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")
        assert resp.status_code == 404

    async def _draft_with_wif(self, db_session: AsyncSession, user: User) -> Draft:
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=user.id,
            name="Test Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            weft_threads=4,
        )
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_renders_and_returns_png(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content[:4] == b"\x89PNG"

    async def test_response_includes_pixels_per_row_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.headers.get("X-Pixels-Per-Row") == str(rendering.DRAWDOWN_SCALE)

    async def test_response_includes_total_rows_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.headers.get("X-Total-Rows") == "4"

    async def test_response_has_cache_control_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"

    async def test_response_has_etag_header(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.headers.get("ETag") == f'"{draft.id}"'

    async def test_413_writes_audit_log(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ):
        draft = await self._draft_with_wif(db_session, test_user)

        def _raise_413(*_a, **_kw):
            raise HTTPException(status_code=413, detail="too big")

        monkeypatch.setattr(rendering, "render_drawdown_only", _raise_413)

        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")

        assert resp.status_code == 413
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.actor_email == test_user.email,
                AuditLog.event_type == "render.limit_exceeded",
            )
        )
        assert entry is not None
        assert entry.details["draft_id"] == str(draft.id)
        assert entry.details["mode"] == "full"


# ---------------------------------------------------------------------------
# GET /{draft_id}/drawdown?start_row=&row_count=  (tiled)
# ---------------------------------------------------------------------------


class TestGetDrawdownTile:
    async def _draft_with_wif(self, db_session: AsyncSession, user: User) -> Draft:
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=user.id,
            name="Test Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            weft_threads=4,
        )
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_returns_png(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.status_code == 200
        assert resp.content[:4] == b"\x89PNG"

    async def test_includes_pixels_per_row_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.headers.get("X-Pixels-Per-Row") is not None

    async def test_includes_total_rows_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.headers.get("X-Total-Rows") == "4"

    async def test_includes_start_row_header(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=1&row_count=2")
        assert resp.headers.get("X-Start-Row") == "1"

    async def test_includes_row_count_header(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.headers.get("X-Row-Count") == "2"

    async def test_no_cache_header_for_tiled_request(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.headers.get("Cache-Control") == "no-store"

    async def test_start_row_only_works(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0")
        assert resp.status_code == 200

    async def test_row_count_only_works(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?row_count=2")
        assert resp.status_code == 200

    async def test_returns_401_when_unauthenticated(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._draft_with_wif(db_session, test_user)
        resp = await client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.status_code == 401

    async def test_413_writes_audit_log(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
    ):
        draft = await self._draft_with_wif(db_session, test_user)

        def _raise_413(*_a, **_kw):
            raise HTTPException(status_code=413, detail="too wide")

        monkeypatch.setattr(rendering, "render_drawdown_tile", _raise_413)

        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")

        assert resp.status_code == 413
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.actor_email == test_user.email,
                AuditLog.event_type == "render.limit_exceeded",
            )
        )
        assert entry is not None
        assert entry.details["draft_id"] == str(draft.id)
        assert entry.details["mode"] == "tile"


# ---------------------------------------------------------------------------
# GET /{draft_id}/drawdown — pre-rendered tile cache (R2)
# ---------------------------------------------------------------------------


class TestGetDrawdownTileCache:
    """Tests that the drawdown tile endpoint serves from pre-rendered R2 tiles when available."""

    _TILE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # minimal fake PNG header

    async def _draft_with_wif_and_dimensions(
        self, db_session: AsyncSession, user: User, warp_threads: int = 8
    ) -> Draft:
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=user.id,
            name="Tile Cache Test",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            warp_threads=warp_threads,
            weft_threads=200,
        )
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_serves_from_cache_on_hit(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        draft = await self._draft_with_wif_and_dimensions(db_session, test_user)
        settings = get_settings()
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // draft.warp_threads, DRAWDOWN_SCALE)

        storage.save_drawdown_tile(draft.id, expected_scale, 0, self._TILE_PNG)

        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count={tile_row_count}")
        assert resp.status_code == 200
        assert resp.content == self._TILE_PNG

    async def test_cache_hit_returns_immutable_cache_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        draft = await self._draft_with_wif_and_dimensions(db_session, test_user)
        settings = get_settings()
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // draft.warp_threads, DRAWDOWN_SCALE)

        storage.save_drawdown_tile(draft.id, expected_scale, 0, self._TILE_PNG)

        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count={tile_row_count}")
        assert "immutable" in (resp.headers.get("Cache-Control") or "")

    async def test_cache_miss_triggers_prerender_task(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _mock_tile_task: MagicMock,
    ):
        from app.config import get_settings

        draft = await self._draft_with_wif_and_dimensions(db_session, test_user)
        tile_row_count = get_settings().tile_row_count

        await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count={tile_row_count}")
        _mock_tile_task.apply_async.assert_called_once_with(args=[str(draft.id)])

    async def test_cache_miss_skips_task_when_t0_exists(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _mock_tile_task: MagicMock,
    ):
        """When t0 already exists (eager prerender ran), lazy trigger must not re-queue."""
        import app.services.storage as storage
        from app.config import get_settings
        from app.services.rendering import DRAWDOWN_SCALE

        draft = await self._draft_with_wif_and_dimensions(db_session, test_user)
        settings = get_settings()
        tile_row_count = settings.tile_row_count
        expected_scale = min(settings.render_max_width // draft.warp_threads, DRAWDOWN_SCALE)

        # Pre-save t0 (simulates completed eager prerender) but not the requested tile
        storage.save_drawdown_tile(draft.id, expected_scale, 0, self._TILE_PNG)

        # Request tile at row 100 — cache miss, but t0 exists so no new task
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=100&row_count={tile_row_count}")
        assert resp.status_code == 200
        _mock_tile_task.apply_async.assert_not_called()

    async def test_non_standard_request_skips_cache_and_task(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _mock_tile_task: MagicMock,
    ):
        """A request with row_count != tile_row_count bypasses the tile cache."""
        draft = await self._draft_with_wif_and_dimensions(db_session, test_user)

        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown?start_row=0&row_count=2")
        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "no-store"
        _mock_tile_task.apply_async.assert_not_called()


# ---------------------------------------------------------------------------
# POST /api/drafts  (WIF upload)
# ---------------------------------------------------------------------------


class TestCreateDraft:
    @pytest.fixture(autouse=True)
    def _use_tmp_upload_dir(self, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))

    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Draft"},
        )
        assert resp.status_code == 201

    async def test_returns_draft_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Draft"},
        )
        data = resp.json()
        assert data["name"] == "My Draft"
        assert data["wif_filename"] == "test.wif"
        assert "has_treadling" in data
        assert "lint_warnings" in data

    async def test_non_wif_extension_returns_400(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("test.txt", b"not a wif", "text/plain")},
            data={"name": "My Draft"},
        )
        assert resp.status_code == 400

    async def test_with_description(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "Described Draft", "description": "A test draft"},
        )
        assert resp.status_code == 201
        assert resp.json()["description"] == "A test draft"

    async def test_appears_in_list(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("list.wif", _WIF, "application/octet-stream")},
            data={"name": "Listed Draft"},
        )
        data = (await auth_client.get("/api/drafts")).json()
        assert any(d["name"] == "Listed Draft" for d in data)

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post(
            "/api/drafts",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Draft"},
        )
        assert resp.status_code == 401

    async def test_wif_extension_but_non_wif_content_returns_400(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("fake.wif", b"not a wif file at all", "application/octet-stream")},
            data={"name": "Bad Draft"},
        )
        assert resp.status_code == 400

    async def test_wif_extension_with_jpeg_content_returns_400(self, auth_client: AsyncClient):
        jpeg_magic = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("photo.wif", jpeg_magic, "application/octet-stream")},
            data={"name": "Bad Draft"},
        )
        assert resp.status_code == 400

    async def test_wif_with_leading_comment_lines_accepted(self, auth_client: AsyncClient, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))
        tempo_weave_wif = b"; exported by Tempo Weave\r\n" + _WIF
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("tempo.wif", tempo_weave_wif, "application/octet-stream")},
            data={"name": "Tempo Draft"},
        )
        assert resp.status_code == 201

    async def test_invalid_wif_error_includes_first_line(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("bad.wif", b"CLEARLY_NOT_WIF\nmore content", "application/octet-stream")},
            data={"name": "Bad Draft"},
        )
        assert resp.status_code == 400
        assert "CLEARLY_NOT_WIF" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/drafts/{draft_id}/preview
# ---------------------------------------------------------------------------


class TestGetPreview:
    async def test_returns_404_when_no_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/preview")
        assert resp.status_code == 404

    async def test_other_users_draft_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = await _insert_draft(db_session, admin_user, wif_path="d/other.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/preview")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(
        self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        resp = await raw_client.get(f"/api/drafts/{draft.id}/preview")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/drafts/{draft_id}/generate-liftplan
# ---------------------------------------------------------------------------


class TestGenerateLiftplan:
    async def _create_draft_with_wif(
        self,
        db_session,
        user: User,
        *,
        has_treadling: bool = True,
        has_tieup: bool = True,
    ) -> Draft:
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        draft = Draft(
            id=draft_id,
            owner_id=user.id,
            name="Liftplan Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=has_treadling,
            has_tieup=has_tieup,
            has_liftplan=False,
            num_shafts=4,
            num_treadles=4,
        )
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._create_draft_with_wif(db_session, test_user)
        resp = await auth_client.post(f"/api/drafts/{draft.id}/generate-liftplan")
        assert resp.status_code == 200

    async def test_has_liftplan_after_generation(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._create_draft_with_wif(db_session, test_user)
        body = (await auth_client.post(f"/api/drafts/{draft.id}/generate-liftplan")).json()
        assert body["has_liftplan"] is True

    async def test_no_treadling_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._create_draft_with_wif(db_session, test_user, has_treadling=False)
        resp = await auth_client.post(f"/api/drafts/{draft.id}/generate-liftplan")
        assert resp.status_code == 400

    async def test_no_tieup_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await self._create_draft_with_wif(db_session, test_user, has_tieup=False)
        resp = await auth_client.post(f"/api/drafts/{draft.id}/generate-liftplan")
        assert resp.status_code == 400

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/drafts/{uuid.uuid4()}/generate-liftplan")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(
        self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await self._create_draft_with_wif(db_session, test_user)
        resp = await raw_client.post(f"/api/drafts/{draft.id}/generate-liftplan")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /{draft_id}/wif
# ---------------------------------------------------------------------------


class TestDownloadWif:
    async def test_returns_wif_bytes(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        mock_storage["drafts/x/original.wif"] = _WIF
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif")
        assert resp.status_code == 200
        assert resp.content == _WIF

    async def test_returns_attachment_header(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        mock_storage["drafts/x/original.wif"] = _WIF
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif")
        assert "attachment" in resp.headers.get("content-disposition", "")

    async def test_returns_404_when_no_wif_path(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif")
        assert resp.status_code == 404

    async def test_nonexistent_draft_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/drafts/{uuid.uuid4()}/wif")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get(f"/api/drafts/{uuid.uuid4()}/wif")
        assert resp.status_code == 401

    async def test_content_disposition_uses_rfc5987_encoding(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        mock_storage["drafts/x/original.wif"] = _WIF
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        draft.wif_filename = 'my "draft".wif'
        await db_session.commit()
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif")
        cd = resp.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in cd
        assert "my%20%22draft%22" in cd or "my%22" in cd  # URL-encoded form in filename*


# ---------------------------------------------------------------------------
# GET /{draft_id}/wif-modified
# ---------------------------------------------------------------------------


class TestDownloadWifModified:
    async def test_returns_modified_wif_bytes(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        mock_storage["drafts/x/modified.wif"] = _WIF
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        draft.wif_modified_path = "drafts/x/modified.wif"
        await db_session.commit()
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif-modified")
        assert resp.status_code == 200
        assert resp.content == _WIF

    async def test_returns_404_when_no_modified_wif(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif-modified")
        assert resp.status_code == 404

    async def test_filename_has_modified_suffix(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        mock_storage["drafts/x/modified.wif"] = _WIF
        draft = await _insert_draft(db_session, test_user, wif_path="drafts/x/original.wif")
        draft.wif_modified_path = "drafts/x/modified.wif"
        await db_session.commit()
        resp = await auth_client.get(f"/api/drafts/{draft.id}/wif-modified")
        assert "modified" in resp.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# POST /{draft_id}/override-metadata
# ---------------------------------------------------------------------------


class TestOverrideMetadata:
    async def _draft_with_wif(self, db_session: AsyncSession, user: User, mock_storage: dict) -> "Draft":
        mock_storage["drafts/x/original.wif"] = _WIF
        draft = await _insert_draft(db_session, user, wif_path="drafts/x/original.wif")
        return draft

    async def test_returns_200(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await self._draft_with_wif(db_session, test_user, mock_storage)
        resp = await auth_client.post(
            f"/api/drafts/{draft.id}/override-metadata",
            json={"field": "num_shafts", "value": 8},
        )
        assert resp.status_code == 200

    async def test_updates_field_in_response(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await self._draft_with_wif(db_session, test_user, mock_storage)
        resp = await auth_client.post(
            f"/api/drafts/{draft.id}/override-metadata",
            json={"field": "num_shafts", "value": 8},
        )
        assert resp.json()["num_shafts"] == 8

    async def test_records_override_in_metadata(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await self._draft_with_wif(db_session, test_user, mock_storage)
        resp = await auth_client.post(
            f"/api/drafts/{draft.id}/override-metadata",
            json={"field": "num_treadles", "value": 6},
        )
        overrides = resp.json().get("metadata_overrides", {})
        assert "num_treadles" in overrides

    async def test_unsupported_field_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await self._draft_with_wif(db_session, test_user, mock_storage)
        resp = await auth_client.post(
            f"/api/drafts/{draft.id}/override-metadata",
            json={"field": "wif_filename", "value": 1},
        )
        assert resp.status_code == 400

    async def test_value_zero_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = await self._draft_with_wif(db_session, test_user, mock_storage)
        resp = await auth_client.post(
            f"/api/drafts/{draft.id}/override-metadata",
            json={"field": "num_shafts", "value": 0},
        )
        assert resp.status_code == 400

    async def test_nonexistent_draft_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            f"/api/drafts/{uuid.uuid4()}/override-metadata",
            json={"field": "num_shafts", "value": 8},
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post(
            f"/api/drafts/{uuid.uuid4()}/override-metadata",
            json={"field": "num_shafts", "value": 8},
        )
        assert resp.status_code == 401


class TestDrawdownPreviewCache:
    """GET /drawdown serves cached preview when available, falls back to live render."""

    async def _draft_with_cached_preview(
        self,
        db_session: AsyncSession,
        user: User,
        mock_storage: dict,
    ) -> Draft:
        import app.services.storage as storage

        draft_id = uuid.uuid4()
        wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
        preview_key = storage.save_drawdown_preview(_fake_png(4, 4))
        draft = Draft(
            id=draft_id,
            owner_id=user.id,
            name="Cached Preview Draft",
            wif_filename="test.wif",
            wif_path=wif_key,
            has_treadling=True,
            num_shafts=4,
            num_treadles=4,
            weft_threads=4,
            drawdown_preview_path=preview_key,
            drawdown_preview_scale=5,
        )
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_has_drawdown_preview_false_when_no_cache(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user, wif_path="d/x.wif")
        data = (await auth_client.get(f"/api/drafts/{draft.id}")).json()
        assert data["has_drawdown_preview"] is False

    async def test_has_drawdown_preview_true_when_cached(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        mock_storage: dict,
    ):
        draft = await self._draft_with_cached_preview(db_session, test_user, mock_storage)
        data = (await auth_client.get(f"/api/drafts/{draft.id}")).json()
        assert data["has_drawdown_preview"] is True

    async def test_cached_drawdown_served_from_storage(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        mock_storage: dict,
    ):
        draft = await self._draft_with_cached_preview(db_session, test_user, mock_storage)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    async def test_cached_drawdown_uses_stored_scale(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        mock_storage: dict,
    ):
        draft = await self._draft_with_cached_preview(db_session, test_user, mock_storage)
        resp = await auth_client.get(f"/api/drafts/{draft.id}/drawdown")
        assert resp.headers.get("X-Pixels-Per-Row") == "5"

    async def test_upload_dispatches_preview_task(
        self, auth_client: AsyncClient, tmp_path, monkeypatch, _mock_preview_task: MagicMock
    ):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))
        await auth_client.post(
            "/api/drafts",
            files={"wif_file": ("test.wif", _WIF, "application/octet-stream")},
            data={"name": "My Draft"},
        )
        _mock_preview_task.delay.assert_called_once()


class TestUploadRateLimit:
    """Verify the rate limit dependency is actually wired into POST /api/drafts."""

    @pytest.fixture(autouse=True)
    def _use_tmp_upload_dir(self, tmp_path, monkeypatch):
        import app.services.storage as _storage

        monkeypatch.setattr(_storage.settings, "upload_dir", str(tmp_path))

    async def test_429_after_limit_exceeded(self, auth_client: AsyncClient):
        from unittest.mock import patch

        import fakeredis.aioredis

        from app.main import app
        from app.routers.drafts import _upload_rate_limit

        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.dependency_overrides.pop(_upload_rate_limit, None)
        try:
            with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake):
                for i in range(30):
                    await auth_client.post(
                        "/api/drafts",
                        files={"wif_file": (f"draft{i}.wif", _WIF, "application/octet-stream")},
                        data={"name": f"Draft {i}"},
                    )
                resp = await auth_client.post(
                    "/api/drafts",
                    files={"wif_file": ("overflow.wif", _WIF, "application/octet-stream")},
                    data={"name": "Overflow"},
                )
            assert resp.status_code == 429
            assert "retry-after" in resp.headers
        finally:
            app.dependency_overrides[_upload_rate_limit] = lambda: None
