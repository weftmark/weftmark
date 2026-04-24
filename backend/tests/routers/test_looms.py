import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loom import Loom, LoomVersion
from app.models.user import User


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
