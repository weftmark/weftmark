"""Tests for the loom catalog (loom_references) endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loom import Loom, LoomReference, LoomVersion
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_ref(db: AsyncSession, brand: str = "Schacht", model: str = "Baby Wolf") -> LoomReference:
    ref = LoomReference(
        brand=brand,
        model_name=model,
        model_series="Wolf Family",
        loom_category="floor_loom",
        shedding_mechanism="jack_rising",
        shaft_count_options=[4, 8],
        treadle_count=[6, 10],
        weaving_width_options_inches=[26.0],
        foldable=True,
        origin_country="USA",
    )
    db.add(ref)
    await db.flush()
    await db.commit()
    return ref


# ---------------------------------------------------------------------------
# Public catalog — list / search / detail
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_public_catalog_list_empty(client: AsyncClient, db_session: AsyncSession):
    resp = await client.get("/api/loom-catalog")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.anyio
async def test_public_catalog_list_returns_entries(client: AsyncClient, db_session: AsyncSession):
    await _make_ref(db_session)
    resp = await client.get("/api/loom-catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["brand"] == "Schacht"
    assert data[0]["model_name"] == "Baby Wolf"


@pytest.mark.anyio
async def test_public_catalog_search_by_brand(client: AsyncClient, db_session: AsyncSession):
    await _make_ref(db_session, brand="Ashford", model="Jack Loom")
    await _make_ref(db_session, brand="Louet", model="Spring II")
    resp = await client.get("/api/loom-catalog/search?q=ashford")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["brand"] == "Ashford"


@pytest.mark.anyio
async def test_public_catalog_search_by_model(client: AsyncClient, db_session: AsyncSession):
    await _make_ref(db_session, brand="Schacht", model="Baby Wolf")
    await _make_ref(db_session, brand="Schacht", model="Mighty Wolf")
    # Search "mighty" — unique enough to match only Mighty Wolf regardless of other test data
    resp = await client.get("/api/loom-catalog/search?q=mighty")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["model_name"] == "Mighty Wolf"


@pytest.mark.anyio
async def test_public_catalog_filter_by_category(client: AsyncClient, db_session: AsyncSession):
    ref1 = LoomReference(brand="TestCatalog", model_name="Rigid Heddle 24", loom_category="rigid_heddle")
    ref2 = LoomReference(brand="TestCatalog", model_name="Floor Loom 4S", loom_category="floor_loom")
    db_session.add_all([ref1, ref2])
    await db_session.commit()

    resp = await client.get("/api/loom-catalog?category=floor_loom")
    assert resp.status_code == 200
    data = resp.json()
    # All returned entries must be floor_loom; at minimum our entry is present
    assert all(d["loom_category"] == "floor_loom" for d in data)
    assert any(d["brand"] == "TestCatalog" and d["model_name"] == "Floor Loom 4S" for d in data)


@pytest.mark.anyio
async def test_public_catalog_detail(client: AsyncClient, db_session: AsyncSession):
    ref = await _make_ref(db_session)
    resp = await client.get(f"/api/loom-catalog/{ref.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(ref.id)
    assert data["shaft_count_options"] == [4, 8]
    assert data["treadle_count"] == [6, 10]
    assert data["foldable"] is True


@pytest.mark.anyio
async def test_public_catalog_detail_404(client: AsyncClient, db_session: AsyncSession):
    import uuid

    resp = await client.get(f"/api/loom-catalog/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_create_loom_reference(admin_client: AsyncClient, db_session: AsyncSession):
    payload = {
        "brand": "Harrisville Designs",
        "model_name": "Traditional Floor Loom",
        "loom_category": "floor_loom",
        "shedding_mechanism": "jack_rising",
        "shaft_count_options": [4, 8],
        "treadle_count": [6, 10],
        "weaving_width_options_inches": [22.0, 36.0, 45.0],
        "foldable": True,
        "mobility_wheels_included": True,
        "origin_country": "USA",
    }
    resp = await admin_client.post("/api/admin/loom-catalog", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["brand"] == "Harrisville Designs"
    assert data["shaft_count_options"] == [4, 8]
    assert data["mobility_wheels_included"] is True


@pytest.mark.anyio
async def test_admin_create_duplicate_rejected(admin_client: AsyncClient, db_session: AsyncSession):
    await _make_ref(db_session)
    payload = {"brand": "Schacht", "model_name": "Baby Wolf", "loom_category": "floor_loom"}
    resp = await admin_client.post("/api/admin/loom-catalog", json=payload)
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_admin_update_loom_reference(admin_client: AsyncClient, db_session: AsyncSession):
    ref = await _make_ref(db_session)
    resp = await admin_client.patch(
        f"/api/admin/loom-catalog/{ref.id}",
        json={"origin_country": "Canada", "foldable": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_country"] == "Canada"
    assert data["foldable"] is False


@pytest.mark.anyio
async def test_admin_delete_loom_reference(admin_client: AsyncClient, db_session: AsyncSession):
    ref = await _make_ref(db_session)
    resp = await admin_client.delete(f"/api/admin/loom-catalog/{ref.id}")
    assert resp.status_code == 204

    resp2 = await admin_client.get(f"/api/loom-catalog/{ref.id}")
    assert resp2.status_code == 404


@pytest.mark.anyio
async def test_non_admin_cannot_create(auth_client: AsyncClient, db_session: AsyncSession):
    payload = {"brand": "Ashford", "model_name": "Test", "loom_category": "floor_loom"}
    resp = await auth_client.post("/api/admin/loom-catalog", json=payload)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Link-reference endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_link_loom_to_reference(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    ref = await _make_ref(db_session)

    loom = Loom(
        owner_id=test_user.id,
        loom_type="floor_loom",
        manufacturer="Schacht",
        model_name="Baby Wolf",
        supports_lift_tracking=False,
        supports_treadle_tracking=True,
    )
    db_session.add(loom)
    await db_session.flush()
    version = LoomVersion(
        loom_id=loom.id,
        version_number=1,
        effective_date=date(2024, 1, 1),
    )
    db_session.add(version)
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/link-reference",
        json={"loom_reference_id": str(ref.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["loom_reference_id"] == str(ref.id)


@pytest.mark.anyio
async def test_unlink_loom_from_reference(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    ref = await _make_ref(db_session)

    loom = Loom(
        owner_id=test_user.id,
        loom_type="floor_loom",
        manufacturer="Schacht",
        model_name="Baby Wolf",
        loom_reference_id=ref.id,
        supports_lift_tracking=False,
        supports_treadle_tracking=True,
    )
    db_session.add(loom)
    await db_session.flush()
    db_session.add(LoomVersion(loom_id=loom.id, version_number=1, effective_date=date(2024, 1, 1)))
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/link-reference",
        json={"loom_reference_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["loom_reference_id"] is None


@pytest.mark.anyio
async def test_link_nonexistent_reference_404(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    import uuid

    loom = Loom(
        owner_id=test_user.id,
        loom_type="floor_loom",
        manufacturer="Unknown",
        model_name="Mystery",
        supports_lift_tracking=False,
        supports_treadle_tracking=True,
    )
    db_session.add(loom)
    await db_session.flush()
    db_session.add(LoomVersion(loom_id=loom.id, version_number=1, effective_date=date(2024, 1, 1)))
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/link-reference",
        json={"loom_reference_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
