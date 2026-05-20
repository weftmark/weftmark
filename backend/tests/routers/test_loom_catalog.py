"""Tests for the loom catalog (loom_references) endpoints."""

import uuid
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
# Link-reference endpoint (per-version)
# ---------------------------------------------------------------------------


async def _make_loom_with_version(
    db: AsyncSession,
    user: "User",
    loom_reference_id: "uuid.UUID | None" = None,
) -> tuple[Loom, LoomVersion]:
    loom = Loom(
        owner_id=user.id,
        loom_type="floor_loom",
        manufacturer="Schacht",
        model_name="Baby Wolf",
        supports_lift_tracking=False,
        supports_treadle_tracking=True,
    )
    db.add(loom)
    await db.flush()
    version = LoomVersion(
        loom_id=loom.id,
        loom_reference_id=loom_reference_id,
        version_number=1,
        effective_date=date(2024, 1, 1),
    )
    db.add(version)
    await db.commit()
    return loom, version


@pytest.mark.anyio
async def test_link_version_to_reference(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    ref = await _make_ref(db_session)
    loom, version = await _make_loom_with_version(db_session, test_user)

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/versions/{version.id}/link-reference",
        json={"loom_reference_id": str(ref.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["loom_reference_id"] == str(ref.id)
    assert data["current_version"]["loom_reference_id"] == str(ref.id)


@pytest.mark.anyio
async def test_unlink_version_from_reference(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    ref = await _make_ref(db_session)
    loom, version = await _make_loom_with_version(db_session, test_user, loom_reference_id=ref.id)

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/versions/{version.id}/link-reference",
        json={"loom_reference_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["loom_reference_id"] is None


@pytest.mark.anyio
async def test_link_nonexistent_reference_404(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    import uuid

    loom, version = await _make_loom_with_version(db_session, test_user)

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/versions/{version.id}/link-reference",
        json={"loom_reference_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_relink_version_to_different_catalog_entry(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    """A version linked to entry A can be relinked to entry B."""
    ref_a = await _make_ref(db_session, brand="Louet", model="Spring 8")
    ref_b = await _make_ref(db_session, brand="Louet", model="Spring 16")
    loom, version = await _make_loom_with_version(db_session, test_user, loom_reference_id=ref_a.id)

    resp = await auth_client.post(
        f"/api/looms/{loom.id}/versions/{version.id}/link-reference",
        json={"loom_reference_id": str(ref_b.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["loom_reference_id"] == str(ref_b.id)
    assert data["loom_reference_brand"] == "Louet"
    assert data["loom_reference_model_name"] == "Spring 16"
    assert data["current_version"]["loom_reference_id"] == str(ref_b.id)


@pytest.mark.anyio
async def test_per_version_catalog_links_independent(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    """v1 and v2 can be linked to different catalog entries independently."""

    ref_8 = await _make_ref(db_session, brand="Louet", model="Jane 8")
    ref_16 = await _make_ref(db_session, brand="Louet", model="Jane 16")

    loom = Loom(
        owner_id=test_user.id,
        loom_type="floor_loom",
        manufacturer="Louet",
        model_name="Jane",
        supports_lift_tracking=False,
        supports_treadle_tracking=True,
    )
    db_session.add(loom)
    await db_session.flush()

    v1 = LoomVersion(loom_id=loom.id, loom_reference_id=ref_8.id, version_number=1, effective_date=date(2023, 1, 1))
    v2 = LoomVersion(loom_id=loom.id, loom_reference_id=ref_16.id, version_number=2, effective_date=date(2024, 6, 1))
    db_session.add_all([v1, v2])
    await db_session.commit()

    resp = await auth_client.get(f"/api/looms/{loom.id}")
    assert resp.status_code == 200
    data = resp.json()

    # Top-level fields reflect the current (latest) version — v2 → ref_16
    assert data["loom_reference_id"] == str(ref_16.id)
    assert data["loom_reference_brand"] == "Louet"
    assert data["loom_reference_model_name"] == "Jane 16"

    # v1 still carries its own link
    versions = {v["version_number"]: v for v in data["versions"]}
    assert versions[1]["loom_reference_id"] == str(ref_8.id)
    assert versions[1]["loom_reference_model_name"] == "Jane 8"
    assert versions[2]["loom_reference_id"] == str(ref_16.id)
    assert versions[2]["loom_reference_model_name"] == "Jane 16"


@pytest.mark.anyio
async def test_linked_loom_detail_includes_catalog_names(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    """GET /api/looms/{id} returns loom_reference_brand/model_name when current version is linked."""
    ref = await _make_ref(db_session, brand="Schacht", model="Baby Wolf")
    loom, _ = await _make_loom_with_version(db_session, test_user, loom_reference_id=ref.id)

    resp = await auth_client.get(f"/api/looms/{loom.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["loom_reference_brand"] == "Schacht"
    assert data["loom_reference_model_name"] == "Baby Wolf"


@pytest.mark.anyio
async def test_unlinked_loom_detail_has_null_catalog_names(
    auth_client: AsyncClient, db_session: AsyncSession, test_user: User
):
    """GET /api/looms/{id} returns null catalog names when not linked."""
    loom, _ = await _make_loom_with_version(db_session, test_user)

    resp = await auth_client.get(f"/api/looms/{loom.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["loom_reference_brand"] is None
    assert data["loom_reference_model_name"] is None


@pytest.mark.anyio
async def test_list_looms_includes_catalog_names(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """GET /api/looms returns catalog names from the current version for linked looms."""
    ref = await _make_ref(db_session, brand="Schacht", model="Mighty Wolf")
    loom, _ = await _make_loom_with_version(db_session, test_user, loom_reference_id=ref.id)

    resp = await auth_client.get("/api/looms")
    assert resp.status_code == 200
    looms = resp.json()
    linked = next((item for item in looms if item["loom_reference_id"] == str(ref.id)), None)
    assert linked is not None
    assert linked["loom_reference_brand"] == "Schacht"
    assert linked["loom_reference_model_name"] == "Mighty Wolf"
