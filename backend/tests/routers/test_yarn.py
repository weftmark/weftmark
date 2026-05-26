import io
import uuid
from decimal import Decimal

from httpx import AsyncClient
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.yarn import Skein, Yarn


def _make_jpeg(width: int = 20, height: int = 20) -> bytes:
    img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yarn_payload(**overrides) -> dict:
    base = {"brand": "Ashford", "name": "Merino DK"}
    base.update(overrides)
    return base


async def _create_yarn(auth_client: AsyncClient, **overrides) -> dict:
    resp = await auth_client.post("/api/yarn", json=_yarn_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/yarn
# ---------------------------------------------------------------------------


class TestCreateYarn:
    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/yarn", json=_yarn_payload())
        assert resp.status_code == 201

    async def test_returns_expected_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/yarn", json=_yarn_payload())
        data = resp.json()
        assert data["brand"] == "Ashford"
        assert data["name"] == "Merino DK"
        assert "id" in data
        assert data["skein_count"] == 0
        assert data["has_photo"] is False

    async def test_optional_fields_null_by_default(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/yarn", json=_yarn_payload())
        data = resp.json()
        assert data["color_name"] is None
        assert data["fiber_content"] is None
        assert data["notes"] is None

    async def test_with_all_optional_fields(self, auth_client: AsyncClient):
        payload = _yarn_payload(
            weight_notation="DK",
            weight_category="light",
            fiber_content="100% merino",
            color_name="Natural",
            color_hex="#F5F5DC",
            unit_yardage="230",
            sett_min=12,
            sett_max=16,
            notes="Nice and soft",
        )
        resp = await auth_client.post("/api/yarn", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["weight_notation"] == "DK"
        assert data["fiber_content"] == "100% merino"
        assert data["color_name"] == "Natural"
        assert data["sett_min"] == 12

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post("/api/yarn", json=_yarn_payload())
        assert resp.status_code == 401

    async def test_persists_to_db(self, auth_client: AsyncClient, db_session: AsyncSession):
        data = await _create_yarn(auth_client)
        yarn_id = uuid.UUID(data["id"])
        result = await db_session.scalar(select(Yarn).where(Yarn.id == yarn_id))
        assert result is not None
        assert result.brand == "Ashford"


# ---------------------------------------------------------------------------
# GET /api/yarn
# ---------------------------------------------------------------------------


class TestListYarn:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/yarn")
        assert resp.status_code == 200

    async def test_empty_list_when_no_yarn(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/yarn")
        assert resp.json() == []

    async def test_returns_created_yarn(self, auth_client: AsyncClient):
        await _create_yarn(auth_client, brand="Cascade")
        resp = await auth_client.get("/api/yarn")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["brand"] == "Cascade"

    async def test_does_not_return_deleted_yarn(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        yarn = Yarn(owner_id=test_user.id, brand="OldBrand", name="OldName")
        db_session.add(yarn)
        await db_session.commit()
        yarn.soft_delete()
        await db_session.commit()

        resp = await auth_client.get("/api/yarn")
        assert all(y["brand"] != "OldBrand" for y in resp.json())

    async def test_does_not_return_other_users_yarn(self, auth_client: AsyncClient, db_session: AsyncSession):
        other_user = User(email="other@example.com", display_name="Other", oidc_sub="other-sub")
        db_session.add(other_user)
        await db_session.flush()
        yarn = Yarn(owner_id=other_user.id, brand="OtherBrand", name="OtherYarn")
        db_session.add(yarn)
        await db_session.commit()

        resp = await auth_client.get("/api/yarn")
        assert all(y["brand"] != "OtherBrand" for y in resp.json())

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/yarn")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/yarn/{yarn_id}
# ---------------------------------------------------------------------------


class TestGetYarn:
    async def test_returns_200(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.get(f"/api/yarn/{data['id']}")
        assert resp.status_code == 200

    async def test_returns_correct_yarn(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client, brand="Malabrigo", name="Worsted")
        resp = await auth_client.get(f"/api/yarn/{data['id']}")
        assert resp.json()["brand"] == "Malabrigo"

    async def test_includes_skeins_list(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.get(f"/api/yarn/{data['id']}")
        assert "skeins" in resp.json()

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/yarn/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_yarn_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession):
        other_user = User(email="other2@example.com", display_name="Other2", oidc_sub="other-sub-2")
        db_session.add(other_user)
        await db_session.flush()
        yarn = Yarn(owner_id=other_user.id, brand="NotMine", name="Yarn")
        db_session.add(yarn)
        await db_session.commit()

        resp = await auth_client.get(f"/api/yarn/{yarn.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get(f"/api/yarn/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/yarn/{yarn_id}
# ---------------------------------------------------------------------------


class TestUpdateYarn:
    async def test_returns_200(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.patch(f"/api/yarn/{data['id']}", json={"brand": "Rowan"})
        assert resp.status_code == 200

    async def test_updates_brand(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.patch(f"/api/yarn/{data['id']}", json={"brand": "Rowan"})
        assert resp.json()["brand"] == "Rowan"

    async def test_updates_notes(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.patch(f"/api/yarn/{data['id']}", json={"notes": "Very soft"})
        assert resp.json()["notes"] == "Very soft"

    async def test_does_not_clobber_other_fields(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client, fiber_content="wool")
        resp = await auth_client.patch(f"/api/yarn/{data['id']}", json={"brand": "New Brand"})
        assert resp.json()["fiber_content"] == "wool"

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/yarn/{uuid.uuid4()}", json={"brand": "X"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.patch(f"/api/yarn/{uuid.uuid4()}", json={"brand": "X"})
        assert resp.status_code == 401

    async def test_persists_to_db(self, auth_client: AsyncClient, db_session: AsyncSession):
        data = await _create_yarn(auth_client)
        await auth_client.patch(f"/api/yarn/{data['id']}", json={"color_name": "Blue"})
        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == uuid.UUID(data["id"])))
        await db_session.refresh(yarn)
        assert yarn.color_name == "Blue"


# ---------------------------------------------------------------------------
# DELETE /api/yarn/{yarn_id}
# ---------------------------------------------------------------------------


class TestDeleteYarn:
    async def test_returns_204(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.delete(f"/api/yarn/{data['id']}")
        assert resp.status_code == 204

    async def test_yarn_not_returned_after_delete(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        await auth_client.delete(f"/api/yarn/{data['id']}")
        resp = await auth_client.get("/api/yarn")
        assert all(y["id"] != data["id"] for y in resp.json())

    async def test_get_after_delete_returns_404(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        await auth_client.delete(f"/api/yarn/{data['id']}")
        resp = await auth_client.get(f"/api/yarn/{data['id']}")
        assert resp.status_code == 404

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/yarn/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.delete(f"/api/yarn/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_soft_deletes_in_db(self, auth_client: AsyncClient, db_session: AsyncSession):
        data = await _create_yarn(auth_client)
        await auth_client.delete(f"/api/yarn/{data['id']}")
        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == uuid.UUID(data["id"])))
        await db_session.refresh(yarn)
        assert yarn.deleted_at is not None


# ---------------------------------------------------------------------------
# POST /api/yarn/{yarn_id}/skeins
# ---------------------------------------------------------------------------


class TestAddSkeins:
    async def test_returns_201(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 1})
        assert resp.status_code == 201

    async def test_returns_list_of_skeins(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 3})
        assert len(resp.json()) == 3

    async def test_default_status_is_available(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 1})
        assert resp.json()[0]["status"] == "available"

    async def test_custom_status(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 1, "status": "in_use"})
        assert resp.json()[0]["status"] == "in_use"

    async def test_with_yardage(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(
            f"/api/yarn/{data['id']}/skeins",
            json={"quantity": 1, "current_yardage": "200.5"},
        )
        assert Decimal(resp.json()[0]["current_yardage"]) == Decimal("200.5")

    async def test_quantity_zero_returns_400(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 0})
        assert resp.status_code == 400

    async def test_quantity_over_100_returns_400(self, auth_client: AsyncClient):
        data = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{data['id']}/skeins", json={"quantity": 101})
        assert resp.status_code == 400

    async def test_nonexistent_yarn_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/yarn/{uuid.uuid4()}/skeins", json={"quantity": 1})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post(f"/api/yarn/{uuid.uuid4()}/skeins", json={"quantity": 1})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/yarn/{yarn_id}/skeins/{skein_id}
# ---------------------------------------------------------------------------


class TestUpdateSkein:
    async def _add_skein(self, auth_client: AsyncClient, yarn_id: str) -> dict:
        resp = await auth_client.post(f"/api/yarn/{yarn_id}/skeins", json={"quantity": 1})
        return resp.json()[0]

    async def test_returns_200(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        skein = await self._add_skein(auth_client, yarn["id"])
        resp = await auth_client.patch(f"/api/yarn/{yarn['id']}/skeins/{skein['id']}", json={"status": "consumed"})
        assert resp.status_code == 200

    async def test_updates_status(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        skein = await self._add_skein(auth_client, yarn["id"])
        resp = await auth_client.patch(f"/api/yarn/{yarn['id']}/skeins/{skein['id']}", json={"status": "consumed"})
        assert resp.json()["status"] == "consumed"

    async def test_updates_yardage(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        skein = await self._add_skein(auth_client, yarn["id"])
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/skeins/{skein['id']}",
            json={"current_yardage": "150.0"},
        )
        assert Decimal(resp.json()["current_yardage"]) == Decimal("150.0")

    async def test_nonexistent_skein_returns_404(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.patch(f"/api/yarn/{yarn['id']}/skeins/{uuid.uuid4()}", json={"status": "consumed"})
        assert resp.status_code == 404

    async def test_nonexistent_yarn_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/yarn/{uuid.uuid4()}/skeins/{uuid.uuid4()}", json={"status": "consumed"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.patch(f"/api/yarn/{uuid.uuid4()}/skeins/{uuid.uuid4()}", json={"status": "consumed"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/yarn/{yarn_id}/skeins/{skein_id}
# ---------------------------------------------------------------------------


class TestDeleteSkein:
    async def _add_skein(self, auth_client: AsyncClient, yarn_id: str) -> dict:
        resp = await auth_client.post(f"/api/yarn/{yarn_id}/skeins", json={"quantity": 1})
        return resp.json()[0]

    async def test_returns_204(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        skein = await self._add_skein(auth_client, yarn["id"])
        resp = await auth_client.delete(f"/api/yarn/{yarn['id']}/skeins/{skein['id']}")
        assert resp.status_code == 204

    async def test_removes_from_db(self, auth_client: AsyncClient, db_session: AsyncSession):
        yarn = await _create_yarn(auth_client)
        skein = await self._add_skein(auth_client, yarn["id"])
        await auth_client.delete(f"/api/yarn/{yarn['id']}/skeins/{skein['id']}")
        result = await db_session.scalar(select(Skein).where(Skein.id == uuid.UUID(skein["id"])))
        assert result is None

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.delete(f"/api/yarn/{yarn['id']}/skeins/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.delete(f"/api/yarn/{uuid.uuid4()}/skeins/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/yarn/{yarn_id}/clone
# ---------------------------------------------------------------------------


class TestCloneYarn:
    async def test_returns_201(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        assert resp.status_code == 201

    async def test_clone_has_same_brand_and_name(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, brand="Cascade", name="220")
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        clone = resp.json()
        assert clone["brand"] == "Cascade"
        assert clone["name"] == "220"

    async def test_clone_is_a_new_yarn(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        assert resp.json()["id"] != yarn["id"]

    async def test_clone_overrides_color_name(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, color_name="Red")
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={"color_name": "Blue"})
        assert resp.json()["color_name"] == "Blue"

    async def test_clone_overrides_color_hex(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, color_hex="#FF0000")
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={"color_hex": "#0000FF"})
        assert resp.json()["color_hex"] == "#0000FF"

    async def test_clone_inherits_source_color_when_not_overridden(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, color_name="Forest Green")
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        assert resp.json()["color_name"] == "Forest Green"

    async def test_clone_has_no_skeins(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.post(f"/api/yarn/{yarn['id']}/skeins", json={"quantity": 5})
        resp = await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        assert resp.json()["skein_count"] == 0

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/yarn/{uuid.uuid4()}/clone", json={})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post(f"/api/yarn/{uuid.uuid4()}/clone", json={})
        assert resp.status_code == 401

    async def test_clone_count_appears_in_list(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.post(f"/api/yarn/{yarn['id']}/clone", json={})
        resp = await auth_client.get("/api/yarn")
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# Photo endpoints (auth/404 only — S3 calls skipped)
# ---------------------------------------------------------------------------


class TestYarnPhotoAuth:
    async def test_get_photo_no_photo_returns_404(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.get(f"/api/yarn/{yarn['id']}/photo")
        assert resp.status_code == 404

    async def test_get_photo_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get(f"/api/yarn/{uuid.uuid4()}/photo")
        assert resp.status_code == 401

    async def test_delete_photo_no_photo_returns_204(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.delete(f"/api/yarn/{yarn['id']}/photo")
        assert resp.status_code == 204

    async def test_delete_photo_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.delete(f"/api/yarn/{uuid.uuid4()}/photo")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Photo upload / get / delete — full flow with real image data
# ---------------------------------------------------------------------------


class TestYarnPhoto:
    async def test_upload_returns_204(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 204

    async def test_get_photo_after_upload_returns_200(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.get(f"/api/yarn/{yarn['id']}/photo")
        assert resp.status_code == 200

    async def test_get_photo_returns_image_bytes(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.get(f"/api/yarn/{yarn['id']}/photo")
        assert len(resp.content) > 0

    async def test_upload_invalid_content_type_returns_400(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_upload_too_large_returns_400(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        big = b"X" * (6 * 1024 * 1024)
        resp = await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", big, "image/jpeg")},
        )
        assert resp.status_code == 400

    async def test_upload_replaces_existing_photo(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("first.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("second.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 204

    async def test_delete_photo_after_upload_returns_204(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        resp = await auth_client.delete(f"/api/yarn/{yarn['id']}/photo")
        assert resp.status_code == 204

    async def test_photo_gone_after_delete(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        await auth_client.delete(f"/api/yarn/{yarn['id']}/photo")
        resp = await auth_client.get(f"/api/yarn/{yarn['id']}/photo")
        assert resp.status_code == 404

    async def test_upload_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.put(
            f"/api/yarn/{uuid.uuid4()}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/yarn/{yarn_id}/colorway (lines 429-442)
# ---------------------------------------------------------------------------


class TestPatchYarnColorway:
    async def test_update_color_name(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, color_name="Red")
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={"color_name": "Blue"},
        )
        assert resp.status_code == 200
        assert resp.json()["color_name"] == "Blue"

    async def test_clear_color_name_with_empty_string(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client, color_name="Red")
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={"color_name": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["color_name"] is None

    async def test_set_colorway_photo_url(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={"colorway_photo_url": "https://example.com/photo.jpg"},
        )
        assert resp.status_code == 200
        assert resp.json()["ravelry_colorway_photo_url"] == "https://example.com/photo.jpg"

    async def test_set_colorway_thumbnail_url(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={"colorway_thumbnail_url": "https://example.com/thumb.jpg"},
        )
        assert resp.status_code == 200
        assert resp.json()["ravelry_colorway_thumbnail_url"] == "https://example.com/thumb.jpg"

    async def test_clear_photos_clears_urls(self, auth_client: AsyncClient):
        yarn = await _create_yarn(auth_client)
        await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={
                "colorway_photo_url": "https://example.com/photo.jpg",
                "colorway_thumbnail_url": "https://example.com/thumb.jpg",
            },
        )
        resp = await auth_client.patch(
            f"/api/yarn/{yarn['id']}/colorway",
            json={"clear_photos": True},
        )
        assert resp.status_code == 200
        assert resp.json()["ravelry_colorway_photo_url"] is None
        assert resp.json()["ravelry_colorway_thumbnail_url"] is None

    async def test_nonexistent_yarn_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(
            f"/api/yarn/{uuid.uuid4()}/colorway",
            json={"color_name": "Blue"},
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.patch(
            f"/api/yarn/{uuid.uuid4()}/colorway",
            json={"color_name": "Blue"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/yarn/{yarn_id}/photo — image processing exception (lines 475-476)
# ---------------------------------------------------------------------------


class TestYarnPhotoImageError:
    async def test_corrupt_image_returns_400(self, auth_client: AsyncClient, monkeypatch):
        from app.routers import yarn as yarn_router

        def _bad_resize(_data):
            raise RuntimeError("corrupt image")

        yarn = await _create_yarn(auth_client)
        monkeypatch.setattr(yarn_router, "resize_to_jpeg", _bad_resize)
        resp = await auth_client.put(
            f"/api/yarn/{yarn['id']}/photo",
            files={"file": ("photo.jpg", _make_jpeg(), "image/jpeg")},
        )
        assert resp.status_code == 400
        assert "Could not process image" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/yarn/properties — lazy fetch when cache is None (lines 349-351)
# ---------------------------------------------------------------------------


class TestGetYarnPropertiesLazyFetch:
    async def test_fetches_when_cache_empty(self, auth_client: AsyncClient, monkeypatch):
        import app.routers.yarn as yarn_router

        monkeypatch.setattr(yarn_router, "_properties_cache", None)
        mock_result = [
            {
                "id": 1,
                "name": "Weight",
                "permalink": "weight",
                "yarn_attributes": [{"id": 10, "name": "DK", "permalink": "dk", "description": None}],
            }
        ]

        from unittest.mock import AsyncMock

        monkeypatch.setattr(
            yarn_router, "_basic_auth_get", AsyncMock(return_value={"yarn_attribute_groups": mock_result})
        )
        resp = await auth_client.get("/api/yarn/properties")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Weight"

    async def test_serves_from_cache_when_populated(self, auth_client: AsyncClient, monkeypatch):
        import app.routers.yarn as yarn_router
        from app.routers.yarn import YarnAttributeGroupSchema

        cached = [YarnAttributeGroupSchema(id=1, name="Weight", permalink="weight", attributes=[])]
        monkeypatch.setattr(yarn_router, "_properties_cache", cached)
        resp = await auth_client.get("/api/yarn/properties")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Weight"
