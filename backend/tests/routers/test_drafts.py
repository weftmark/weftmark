"""Tests for the /api/drafts router."""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
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
