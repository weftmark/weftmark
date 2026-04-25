import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.loom import Loom, LoomVersion
from app.models.project import Project
from app.models.user import User

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


async def _insert_project(db_session: AsyncSession, owner: User) -> Project:
    """Insert a project with a real WIF stored at a temp path."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".wif", delete=False)
    tmp.write(_WIF)
    tmp.close()

    project = Project(
        owner_id=owner.id,
        name="Test Project",
        wif_filename="test.wif",
        wif_path=tmp.name,
        has_treadling=True,
        has_liftplan=True,
        num_shafts=4,
        num_treadles=2,
        weft_threads=2,
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _insert_loom(db_session: AsyncSession, owner: User, **kwargs) -> tuple[Loom, LoomVersion]:
    loom = Loom(
        owner_id=owner.id,
        loom_type=kwargs.get("loom_type", "floor_loom"),
        manufacturer=kwargs.get("manufacturer", "Ashford"),
        model_name=kwargs.get("model_name", "Table Loom 8"),
        supports_treadle_tracking=kwargs.get("supports_treadle_tracking", True),
        supports_lift_tracking=kwargs.get("supports_lift_tracking", True),
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


async def _insert_active_activity(db_session: AsyncSession, owner: User, project: Project, loom: Loom) -> Activity:
    activity = Activity(
        owner_id=owner.id,
        project_id=project.id,
        loom_id=loom.id,
        name="Existing activity",
        activity_type="treadle",
        status="active",
        current_pick=1,
        total_picks=2,
    )
    db_session.add(activity)
    await db_session.commit()
    return activity


def _base_payload(project_id: str, **overrides) -> dict:
    return {
        "name": "My activity",
        "project_id": project_id,
        "activity_type": "treadle",
        **overrides,
    }


# ---------------------------------------------------------------------------
# TestCreateActivity
# ---------------------------------------------------------------------------


class TestCreateActivity:
    async def test_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id)))
        assert resp.status_code == 201

    async def test_returns_activity_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id)))
        body = resp.json()
        assert body["name"] == "My activity"
        assert body["activity_type"] == "treadle"
        assert body["status"] == "active"
        assert body["current_pick"] == 1

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await client.post("/api/activities", json=_base_payload(str(project.id)))
        assert resp.status_code == 401

    async def test_unknown_project_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/activities", json=_base_payload(str(uuid.uuid4())))
        assert resp.status_code == 404

    async def test_invalid_activity_type_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id), activity_type="invalid"))
        assert resp.status_code == 400

    async def test_with_valid_loom_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id), loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_with_valid_loom_version_returns_201(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/activities",
            json=_base_payload(str(project.id), loom_id=str(loom.id), loom_version_id=str(version.id)),
        )
        assert resp.status_code == 201
        assert resp.json()["loom_version_id"] == str(version.id)

    async def test_loom_version_from_other_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom_a, _ = await _insert_loom(db_session, test_user)
        loom_b, version_b = await _insert_loom(db_session, test_user, model_name="Other Loom")
        resp = await auth_client.post(
            "/api/activities",
            json=_base_payload(str(project.id), loom_id=str(loom_a.id), loom_version_id=str(version_b.id)),
        )
        assert resp.status_code == 400

    async def test_loom_version_without_loom_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        _, version = await _insert_loom(db_session, test_user)
        resp = await auth_client.post(
            "/api/activities",
            json=_base_payload(str(project.id), loom_version_id=str(version.id)),
        )
        assert resp.status_code == 400

    async def test_second_active_activity_on_same_loom_returns_409(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        await _insert_active_activity(db_session, test_user, project, loom)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id), loom_id=str(loom.id)))
        assert resp.status_code == 409

    async def test_completed_activity_does_not_block_new_one(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom, _ = await _insert_loom(db_session, test_user)
        existing = await _insert_active_activity(db_session, test_user, project, loom)
        existing.status = "completed"
        await db_session.commit()
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id), loom_id=str(loom.id)))
        assert resp.status_code == 201

    async def test_other_users_loom_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        project = await _insert_project(db_session, test_user)
        loom, _ = await _insert_loom(db_session, admin_user)
        resp = await auth_client.post("/api/activities", json=_base_payload(str(project.id), loom_id=str(loom.id)))
        assert resp.status_code == 404
