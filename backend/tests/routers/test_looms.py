import io
import uuid
from datetime import date

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loom import Loom, LoomVersion, LoomVersionAccessory
from app.models.user import User


def _fake_png(width: int = 40, height: int = 40) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _insert_loom_for_user(db_session: AsyncSession, owner: User) -> Loom:
    """Insert a loom owned by `owner` directly into the DB (avoids client override conflict)."""
    loom = Loom(
        owner_id=owner.id,
        loom_type=_LOOM_PAYLOAD["loom_type"],
        manufacturer=_LOOM_PAYLOAD["manufacturer"],
        model_name=_LOOM_PAYLOAD["model_name"],
    )
    db_session.add(loom)
    await db_session.flush()
    version = LoomVersion(
        loom_id=loom.id,
        version_number=1,
        effective_date=date.fromisoformat(_LOOM_PAYLOAD["effective_date"]),
        description="Initial configuration",
        num_shafts=_LOOM_PAYLOAD["num_shafts"],
        num_treadles=_LOOM_PAYLOAD["num_treadles"],
    )
    db_session.add(version)
    await db_session.commit()
    return loom


_LOOM_PAYLOAD = {
    "loom_type": "floor_loom",
    "manufacturer": "Ashford",
    "model_name": "Table Loom 8",
    "effective_date": "2024-01-01",
    "num_shafts": 8,
    "num_treadles": 10,
}


async def _create_loom(auth_client: AsyncClient, payload: dict | None = None) -> dict:
    resp = await auth_client.post("/api/looms", json=payload or _LOOM_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()


class TestCreateLoom:
    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/looms", json=_LOOM_PAYLOAD)
        assert resp.status_code == 201

    async def test_returns_loom_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/looms", json=_LOOM_PAYLOAD)
        body = resp.json()
        assert body["manufacturer"] == "Ashford"
        assert body["model_name"] == "Table Loom 8"
        assert body["loom_type"] == "floor_loom"

    async def test_initial_version_created(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/looms", json=_LOOM_PAYLOAD)
        body = resp.json()
        assert body["current_version"] is not None
        assert body["current_version"]["num_shafts"] == 8
        assert body["current_version"]["num_treadles"] == 10

    async def test_version_number_is_1(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/looms", json=_LOOM_PAYLOAD)
        assert resp.json()["current_version"]["version_number"] == 1

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/looms", json=_LOOM_PAYLOAD)
        assert resp.status_code == 401

    async def test_optional_fields_nullable(self, auth_client: AsyncClient):
        payload = {**_LOOM_PAYLOAD, "serial_number": None, "notes": None}
        resp = await auth_client.post("/api/looms", json=payload)
        body = resp.json()
        assert body["serial_number"] is None
        assert body["notes"] is None


class TestListLooms:
    async def test_empty_list(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/looms")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_created_loom(self, auth_client: AsyncClient):
        await _create_loom(auth_client)
        resp = await auth_client.get("/api/looms")
        assert len(resp.json()) == 1

    async def test_returns_multiple_looms(self, auth_client: AsyncClient):
        await _create_loom(auth_client)
        await _create_loom(auth_client, {**_LOOM_PAYLOAD, "model_name": "Second Loom"})
        resp = await auth_client.get("/api/looms")
        assert len(resp.json()) == 2

    async def test_does_not_return_other_users_looms(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        await _insert_loom_for_user(db_session, admin_user)
        resp = await auth_client.get("/api/looms")
        assert resp.json() == []

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/looms")
        assert resp.status_code == 401


class TestGetLoom:
    async def test_returns_200(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert resp.status_code == 200

    async def test_returns_correct_loom(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert resp.json()["id"] == loom["id"]

    async def test_includes_versions(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert len(resp.json()["versions"]) == 1

    async def test_not_found_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/looms/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        loom = await _insert_loom_for_user(db_session, admin_user)
        resp = await auth_client.get(f"/api/looms/{loom.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/looms/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestUpdateLoom:
    async def test_returns_200(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.patch(f"/api/looms/{loom['id']}", json={"notes": "Updated"})
        assert resp.status_code == 200

    async def test_updates_field(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.patch(f"/api/looms/{loom['id']}", json={"notes": "My loom notes"})
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert resp.json()["notes"] == "My loom notes"

    async def test_updates_manufacturer(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.patch(f"/api/looms/{loom['id']}", json={"manufacturer": "Leclerc"})
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert resp.json()["manufacturer"] == "Leclerc"

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        loom = await _insert_loom_for_user(db_session, admin_user)
        resp = await auth_client.patch(f"/api/looms/{loom.id}", json={"notes": "x"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.patch(f"/api/looms/{uuid.uuid4()}", json={"notes": "x"})
        assert resp.status_code == 401


class TestDeleteLoom:
    async def test_returns_204(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.delete(f"/api/looms/{loom['id']}")
        assert resp.status_code == 204

    async def test_deleted_loom_not_in_list(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.delete(f"/api/looms/{loom['id']}")
        resp = await auth_client.get("/api/looms")
        assert resp.json() == []

    async def test_deleted_loom_returns_404(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.delete(f"/api/looms/{loom['id']}")
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert resp.status_code == 404

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        loom = await _insert_loom_for_user(db_session, admin_user)
        resp = await auth_client.delete(f"/api/looms/{loom.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.delete(f"/api/looms/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{loom_id}/versions
# ---------------------------------------------------------------------------


class TestAddVersion:
    _VERSION_PAYLOAD = {
        "effective_date": "2024-06-01",
        "num_shafts": 8,
        "num_treadles": 10,
        "description": "Added second beam",
    }

    async def test_returns_201(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions", json=self._VERSION_PAYLOAD)
        assert resp.status_code == 201

    async def test_returns_version_fields(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions", json=self._VERSION_PAYLOAD)
        data = resp.json()
        assert data["num_shafts"] == 8
        assert data["description"] == "Added second beam"

    async def test_version_number_increments(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions", json=self._VERSION_PAYLOAD)
        assert resp.json()["version_number"] == 2

    async def test_loom_now_has_two_versions(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.post(f"/api/looms/{loom['id']}/versions", json=self._VERSION_PAYLOAD)
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        assert len(resp.json()["versions"]) == 2

    async def test_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(f"/api/looms/{uuid.uuid4()}/versions", json=self._VERSION_PAYLOAD)
        assert resp.status_code == 404

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        loom = await _insert_loom_for_user(db_session, admin_user)
        resp = await auth_client.post(f"/api/looms/{loom.id}/versions", json=self._VERSION_PAYLOAD)
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(f"/api/looms/{uuid.uuid4()}/versions", json=self._VERSION_PAYLOAD)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /{loom_id}/versions/{version_id}
# ---------------------------------------------------------------------------


class TestUpdateVersion:
    async def _get_version_id(self, auth_client: AsyncClient) -> tuple[str, str]:
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        return loom["id"], version_id

    async def test_returns_200(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_version_id(auth_client)
        resp = await auth_client.patch(f"/api/looms/{loom_id}/versions/{version_id}", json={"name": "Initial setup"})
        assert resp.status_code == 200

    async def test_updates_name(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_version_id(auth_client)
        await auth_client.patch(f"/api/looms/{loom_id}/versions/{version_id}", json={"name": "8-shaft floor"})
        resp = await auth_client.get(f"/api/looms/{loom_id}")
        version = next(v for v in resp.json()["versions"] if v["id"] == version_id)
        assert version["name"] == "8-shaft floor"

    async def test_updates_description(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_version_id(auth_client)
        resp = await auth_client.patch(
            f"/api/looms/{loom_id}/versions/{version_id}", json={"description": "Updated desc"}
        )
        assert resp.json()["description"] == "Updated desc"

    async def test_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404

    async def test_unknown_version_returns_404(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.patch(f"/api/looms/{loom['id']}/versions/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.patch(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{loom_id}/versions/{version_id}/clone
# ---------------------------------------------------------------------------


class TestCloneVersion:
    _CLONE_PAYLOAD = {"effective_date": "2025-01-01", "name": "Cloned", "include_accessories": True}

    async def test_returns_201(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/clone", json=self._CLONE_PAYLOAD)
        assert resp.status_code == 201

    async def test_cloned_version_has_incremented_number(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/clone", json=self._CLONE_PAYLOAD)
        assert resp.json()["version_number"] == 2

    async def test_cloned_version_inherits_shafts(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/clone", json=self._CLONE_PAYLOAD)
        assert resp.json()["num_shafts"] == loom["current_version"]["num_shafts"]

    async def test_clone_without_accessories(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        # First add an accessory to the source version
        await auth_client.post(
            f"/api/looms/{loom['id']}/versions/{version_id}/accessories", json={"name": "Fly shuttle"}
        )
        payload = {**self._CLONE_PAYLOAD, "include_accessories": False}
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/clone", json=payload)
        assert resp.json()["accessories"] == []

    async def test_clone_with_accessories_copies_them(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/accessories", json={"name": "Back beam"})
        resp = await auth_client.post(f"/api/looms/{loom['id']}/versions/{version_id}/clone", json=self._CLONE_PAYLOAD)
        assert len(resp.json()["accessories"]) == 1
        assert resp.json()["accessories"][0]["name"] == "Back beam"

    async def test_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/clone", json=self._CLONE_PAYLOAD
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/clone", json=self._CLONE_PAYLOAD)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{loom_id}/versions/{version_id}/accessories
# ---------------------------------------------------------------------------


class TestAddAccessory:
    async def test_returns_201(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(
            f"/api/looms/{loom['id']}/versions/{version_id}/accessories", json={"name": "Fly shuttle"}
        )
        assert resp.status_code == 201

    async def test_returns_accessory_fields(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(
            f"/api/looms/{loom['id']}/versions/{version_id}/accessories", json={"name": "Fly shuttle"}
        )
        data = resp.json()
        assert data["name"] == "Fly shuttle"
        assert "id" in data

    async def test_accessory_appears_in_version(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        await auth_client.post(
            f"/api/looms/{loom['id']}/versions/{version_id}/accessories", json={"name": "Boat shuttle"}
        )
        resp = await auth_client.get(f"/api/looms/{loom['id']}")
        version = next(v for v in resp.json()["versions"] if v["id"] == version_id)
        assert any(a["name"] == "Boat shuttle" for a in version["accessories"])

    async def test_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/accessories", json={"name": "x"}
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/accessories", json={"name": "x"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /{loom_id}/versions/{version_id}/accessories/{accessory_id}
# ---------------------------------------------------------------------------


class TestDeleteAccessory:
    async def _create_accessory(self, auth_client: AsyncClient) -> tuple[str, str, str]:
        loom = await _create_loom(auth_client)
        loom_id = loom["id"]
        version_id = loom["current_version"]["id"]
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/accessories", json={"name": "Umbrella swift"}
        )
        acc_id = resp.json()["id"]
        return loom_id, version_id, acc_id

    async def test_returns_204(self, auth_client: AsyncClient):
        loom_id, version_id, acc_id = await self._create_accessory(auth_client)
        resp = await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/accessories/{acc_id}")
        assert resp.status_code == 204

    async def test_accessory_removed_from_db(self, auth_client: AsyncClient, db_session: AsyncSession):
        loom_id, version_id, acc_id = await self._create_accessory(auth_client)
        await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/accessories/{acc_id}")
        db_session.expire_all()
        row = await db_session.scalar(select(LoomVersionAccessory).where(LoomVersionAccessory.id == uuid.UUID(acc_id)))
        assert row is None

    async def test_unknown_accessory_returns_404(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        version_id = loom["current_version"]["id"]
        resp = await auth_client.delete(f"/api/looms/{loom['id']}/versions/{version_id}/accessories/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.delete(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/accessories/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.delete(f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/accessories/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Loom tracking flags — derived from loom_type, never from client input
# ---------------------------------------------------------------------------


class TestLoomTrackingFlags:
    async def test_floor_loom_sets_treadle_tracking(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/looms", json=_LOOM_PAYLOAD)
        body = resp.json()
        assert body["supports_treadle_tracking"] is True
        assert body["supports_lift_tracking"] is False

    async def test_table_loom_sets_lift_tracking(self, auth_client: AsyncClient):
        payload = {**_LOOM_PAYLOAD, "loom_type": "table_loom"}
        resp = await auth_client.post("/api/looms", json=payload)
        body = resp.json()
        assert body["supports_lift_tracking"] is True
        assert body["supports_treadle_tracking"] is False

    async def test_unsupported_type_clears_both_flags(self, auth_client: AsyncClient):
        for loom_type in ("rigid_heddle", "inkle", "dobby", "other"):
            payload = {**_LOOM_PAYLOAD, "loom_type": loom_type}
            resp = await auth_client.post("/api/looms", json=payload)
            body = resp.json()
            assert body["supports_treadle_tracking"] is False, f"{loom_type} should not set treadle"
            assert body["supports_lift_tracking"] is False, f"{loom_type} should not set lift"

    async def test_dobby_can_be_created(self, auth_client: AsyncClient):
        payload = {**_LOOM_PAYLOAD, "loom_type": "dobby"}
        resp = await auth_client.post("/api/looms", json=payload)
        assert resp.status_code == 201
        assert resp.json()["loom_type"] == "dobby"

    async def test_changing_type_updates_tracking_flags(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        assert loom["loom_type"] == "floor_loom"
        assert loom["supports_treadle_tracking"] is True

        resp = await auth_client.patch(f"/api/looms/{loom['id']}", json={"loom_type": "table_loom"})
        body = resp.json()
        assert body["loom_type"] == "table_loom"
        assert body["supports_lift_tracking"] is True
        assert body["supports_treadle_tracking"] is False

    async def test_changing_to_unsupported_type_clears_flags(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.patch(f"/api/looms/{loom['id']}", json={"loom_type": "dobby"})
        body = resp.json()
        assert body["supports_treadle_tracking"] is False
        assert body["supports_lift_tracking"] is False


# ---------------------------------------------------------------------------
# PUT/DELETE/GET /{loom_id}/photo
# ---------------------------------------------------------------------------


class TestLoomPhoto:
    async def test_upload_returns_204(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.put(
            f"/api/looms/{loom['id']}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        assert resp.status_code == 204

    async def test_upload_invalid_content_type_returns_400(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.put(
            f"/api/looms/{loom['id']}/photo",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_get_photo_returns_200_after_upload(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.put(
            f"/api/looms/{loom['id']}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        resp = await auth_client.get(f"/api/looms/{loom['id']}/photo")
        assert resp.status_code == 200

    async def test_get_photo_returns_404_when_no_photo(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom['id']}/photo")
        assert resp.status_code == 404

    async def test_delete_photo_returns_204(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.put(
            f"/api/looms/{loom['id']}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        resp = await auth_client.delete(f"/api/looms/{loom['id']}/photo")
        assert resp.status_code == 204

    async def test_delete_photo_clears_it(self, auth_client: AsyncClient):
        loom = await _create_loom(auth_client)
        await auth_client.put(
            f"/api/looms/{loom['id']}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        await auth_client.delete(f"/api/looms/{loom['id']}/photo")
        resp = await auth_client.get(f"/api/looms/{loom['id']}/photo")
        assert resp.status_code == 404

    async def test_upload_unknown_loom_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.put(
            f"/api/looms/{uuid.uuid4()}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.put(
            f"/api/looms/{uuid.uuid4()}/photo",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST/GET/DELETE /{loom_id}/versions/{version_id}/photos
# ---------------------------------------------------------------------------


class TestVersionPhoto:
    async def _get_ids(self, auth_client: AsyncClient) -> tuple[str, str]:
        loom = await _create_loom(auth_client)
        return loom["id"], loom["current_version"]["id"]

    async def test_upload_returns_201(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/photos",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        assert resp.status_code == 201

    async def test_upload_returns_photo_fields(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/photos",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "photo.png"
        assert body["display_order"] == 0

    async def test_get_photo_returns_200(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        upload = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/photos",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        photo_id = upload.json()["id"]
        resp = await auth_client.get(f"/api/looms/{loom_id}/versions/{version_id}/photos/{photo_id}")
        assert resp.status_code == 200

    async def test_get_unknown_photo_returns_404(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom_id}/versions/{version_id}/photos/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_photo_returns_204(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        upload = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/photos",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        photo_id = upload.json()["id"]
        resp = await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/photos/{photo_id}")
        assert resp.status_code == 204

    async def test_delete_unknown_photo_returns_404(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/photos/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_upload_invalid_type_returns_400(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/photos",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(
            f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/photos",
            files={"file": ("photo.png", _fake_png(), "image/png")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST/GET/DELETE /{loom_id}/versions/{version_id}/receipts
# ---------------------------------------------------------------------------


class TestVersionReceipt:
    async def _get_ids(self, auth_client: AsyncClient) -> tuple[str, str]:
        loom = await _create_loom(auth_client)
        return loom["id"], loom["current_version"]["id"]

    async def test_upload_returns_201(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/receipts",
            files={"file": ("receipt.jpg", _fake_png(), "image/jpeg")},
        )
        assert resp.status_code == 201

    async def test_upload_returns_receipt_fields(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/receipts",
            files={"file": ("receipt.jpg", _fake_png(), "image/jpeg")},
        )
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "receipt.jpg"

    async def test_get_receipt_returns_200(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        upload = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/receipts",
            files={"file": ("receipt.jpg", _fake_png(), "image/jpeg")},
        )
        receipt_id = upload.json()["id"]
        resp = await auth_client.get(f"/api/looms/{loom_id}/versions/{version_id}/receipts/{receipt_id}")
        assert resp.status_code == 200

    async def test_get_unknown_receipt_returns_404(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.get(f"/api/looms/{loom_id}/versions/{version_id}/receipts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_receipt_returns_204(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        upload = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/receipts",
            files={"file": ("receipt.jpg", _fake_png(), "image/jpeg")},
        )
        receipt_id = upload.json()["id"]
        resp = await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/receipts/{receipt_id}")
        assert resp.status_code == 204

    async def test_delete_unknown_receipt_returns_404(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.delete(f"/api/looms/{loom_id}/versions/{version_id}/receipts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_upload_invalid_type_returns_400(self, auth_client: AsyncClient):
        loom_id, version_id = await self._get_ids(auth_client)
        resp = await auth_client.post(
            f"/api/looms/{loom_id}/versions/{version_id}/receipts",
            files={"file": ("file.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(
            f"/api/looms/{uuid.uuid4()}/versions/{uuid.uuid4()}/receipts",
            files={"file": ("receipt.jpg", _fake_png(), "image/jpeg")},
        )
        assert resp.status_code == 401
