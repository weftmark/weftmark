"""Tests for app.tasks.purge._purge and _safe_delete.

_purge creates its own DB engine via local imports of create_async_engine /
sessionmaker, so we patch those at the sqlalchemy module level and redirect
them to the test db_session.  This lets us exercise the real SQL logic without
a separate connection.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.purge import _purge, _safe_delete

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def _session_factory(db: AsyncSession):
    """Return a sessionmaker-compatible callable that yields db as the session."""

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass

    class _Factory:
        def __call__(self, *args, **kwargs):
            return _Ctx()

    return _Factory()


@pytest.fixture()
def mock_engine_and_session(db_session: AsyncSession):
    """Patch engine/session creation so _purge runs against db_session."""
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("sqlalchemy.orm.sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


# ---------------------------------------------------------------------------
# TestSafeDelete
# ---------------------------------------------------------------------------


class TestSafeDelete:
    def test_calls_storage_delete(self):
        mock_storage = MagicMock()
        _safe_delete(mock_storage, "drafts/some.wif")
        mock_storage._delete.assert_called_once_with("drafts/some.wif")

    def test_swallows_exceptions(self):
        mock_storage = MagicMock()
        mock_storage._delete.side_effect = Exception("storage unavailable")
        _safe_delete(mock_storage, "drafts/some.wif")  # must not raise

    def test_logs_on_exception(self, caplog):
        import logging

        mock_storage = MagicMock()
        mock_storage._delete.side_effect = RuntimeError("boom")
        with caplog.at_level(logging.WARNING, logger="app.tasks.purge"):
            _safe_delete(mock_storage, "bad/path.wif")
        assert "purge_storage_error" in caplog.text


# ---------------------------------------------------------------------------
# TestPurgeEmpty — no deleted records; covers main control flow
# ---------------------------------------------------------------------------


class TestPurgeEmpty:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(self, db_session, mock_engine_and_session):
        result = await _purge(7)
        assert "projects" in result
        assert "yarn" in result
        assert "looms" in result
        assert "drafts" in result
        assert "total" in result
        assert "retention_days" in result

    @pytest.mark.asyncio
    async def test_all_counts_zero_when_no_deleted_records(self, db_session, mock_engine_and_session):
        result = await _purge(7)
        assert result["projects"] == 0
        assert result["yarn"] == 0
        assert result["looms"] == 0
        assert result["drafts"] == 0
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_retention_days_echoed(self, db_session, mock_engine_and_session):
        result = await _purge(30)
        assert result["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_engine_disposed(self, db_session, mock_engine_and_session):
        await _purge(7)
        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestPurgeDrafts — with actual soft-deleted draft records
# ---------------------------------------------------------------------------


class TestPurgeDrafts:
    @pytest.mark.asyncio
    async def test_deletes_old_soft_deleted_draft(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Old Draft",
            wif_filename="old.wif",
            wif_path="drafts/old.wif",
            deleted_at=_ago(days=30),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _purge(7)

        assert result["drafts"] >= 1
        remaining = (await db_session.scalars(select(Draft))).all()
        assert all(str(d.id) != str(draft.id) for d in remaining)

    @pytest.mark.asyncio
    async def test_keeps_recently_soft_deleted_draft(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Recent Draft",
            wif_filename="recent.wif",
            wif_path="drafts/recent.wif",
            deleted_at=_ago(days=1),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _purge(7)

        assert result["drafts"] == 0
        remaining = (await db_session.scalars(select(Draft))).all()
        assert any(str(d.id) == str(draft.id) for d in remaining)

    @pytest.mark.asyncio
    async def test_keeps_non_deleted_draft(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Active Draft",
            wif_filename="active.wif",
            wif_path="drafts/active.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _purge(7)

        assert result["drafts"] == 0
        remaining = (await db_session.scalars(select(Draft))).all()
        assert any(str(d.id) == str(draft.id) for d in remaining)

    @pytest.mark.asyncio
    async def test_deletes_preview_storage_path(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Preview Draft",
            wif_filename="preview.wif",
            wif_path="drafts/preview.wif",
            preview_path="previews/preview.svg",
            drawdown_preview_path="drawdown-previews/preview.png",
            deleted_at=_ago(days=30),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _purge(7)
        assert result["drafts"] >= 1


# ---------------------------------------------------------------------------
# TestPurgeYarn — with actual soft-deleted yarn records
# ---------------------------------------------------------------------------


class TestPurgeYarn:
    @pytest.mark.asyncio
    async def test_deletes_old_soft_deleted_yarn(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="OldBrand",
            name="OldYarn",
            deleted_at=_ago(days=30),
        )
        db_session.add(yarn)
        await db_session.commit()

        result = await _purge(7)

        assert result["yarn"] >= 1
        remaining = (await db_session.scalars(select(Yarn))).all()
        assert all(str(y.id) != str(yarn.id) for y in remaining)

    @pytest.mark.asyncio
    async def test_keeps_recently_deleted_yarn(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="NewBrand",
            name="NewYarn",
            deleted_at=_ago(days=1),
        )
        db_session.add(yarn)
        await db_session.commit()

        result = await _purge(7)

        assert result["yarn"] == 0
        remaining = (await db_session.scalars(select(Yarn))).all()
        assert any(str(y.id) == str(yarn.id) for y in remaining)


# ---------------------------------------------------------------------------
# TestPurgeLooms — with actual soft-deleted loom records
# ---------------------------------------------------------------------------


class TestPurgeLooms:
    @pytest.mark.asyncio
    async def test_deletes_old_soft_deleted_loom(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.loom import Loom

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor",
            manufacturer="Acme",
            model_name="OldLoom",
            deleted_at=_ago(days=30),
        )
        db_session.add(loom)
        await db_session.commit()

        result = await _purge(7)

        assert result["looms"] >= 1
        remaining = (await db_session.scalars(select(Loom))).all()
        assert all(str(lm.id) != str(loom.id) for lm in remaining)

    @pytest.mark.asyncio
    async def test_keeps_recently_deleted_loom(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.loom import Loom

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="table",
            manufacturer="BrandX",
            model_name="RecentLoom",
            deleted_at=_ago(days=1),
        )
        db_session.add(loom)
        await db_session.commit()

        result = await _purge(7)

        assert result["looms"] == 0
        remaining = (await db_session.scalars(select(Loom))).all()
        assert any(str(lm.id) == str(loom.id) for lm in remaining)


# ---------------------------------------------------------------------------
# TestPurgeProjects — with actual soft-deleted project records and photos
# ---------------------------------------------------------------------------


class TestPurgeProjects:
    async def _make_draft(self, db_session, test_user, suffix=""):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name=f"ProjDraft{suffix}",
            wif_filename=f"proj{suffix}.wif",
            wif_path=f"drafts/proj{suffix}.wif",
        )
        db_session.add(draft)
        await db_session.flush()
        return draft

    @pytest.mark.asyncio
    async def test_deletes_old_soft_deleted_project(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.project import Project

        draft = await self._make_draft(db_session, test_user, suffix="-del")
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Old Project",
            project_type="treadle",
            total_picks=4,
            deleted_at=_ago(days=30),
        )
        db_session.add(project)
        await db_session.commit()

        result = await _purge(7)

        assert result["projects"] >= 1
        remaining = (await db_session.scalars(select(Project))).all()
        assert all(str(p.id) != str(project.id) for p in remaining)

    @pytest.mark.asyncio
    async def test_deletes_project_photos_before_project(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.project import Project, ProjectPhoto

        draft = await self._make_draft(db_session, test_user, suffix="-photo")
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Photo Project",
            project_type="treadle",
            total_picks=4,
            deleted_at=_ago(days=30),
        )
        db_session.add(project)
        await db_session.flush()

        photo = ProjectPhoto(
            id=uuid.uuid4(),
            project_id=project.id,
            file_path="projects/photo.jpg",
            filename="photo.jpg",
        )
        db_session.add(photo)
        await db_session.commit()

        result = await _purge(7)

        assert result["projects"] >= 1
        remaining_photos = (await db_session.scalars(select(ProjectPhoto))).all()
        assert all(str(p.id) != str(photo.id) for p in remaining_photos)

    @pytest.mark.asyncio
    async def test_keeps_recently_deleted_project(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.project import Project

        draft = await self._make_draft(db_session, test_user, suffix="-recent")
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Recent Project",
            project_type="treadle",
            total_picks=4,
            deleted_at=_ago(days=1),
        )
        db_session.add(project)
        await db_session.commit()

        result = await _purge(7)

        assert result["projects"] == 0
        remaining = (await db_session.scalars(select(Project))).all()
        assert any(str(p.id) == str(project.id) for p in remaining)


# ---------------------------------------------------------------------------
# TestPurgeYarnWithPhoto — yarn deletion with photo_path storage cleanup
# ---------------------------------------------------------------------------


class TestPurgeYarnWithPhoto:
    @pytest.mark.asyncio
    async def test_deletes_yarn_with_photo_path(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="PhotoBrand",
            name="PhotoYarn",
            photo_path="yarn/photo.jpg",
            deleted_at=_ago(days=30),
        )
        db_session.add(yarn)
        await db_session.commit()

        result = await _purge(7)

        assert result["yarn"] >= 1
        remaining = (await db_session.scalars(select(Yarn))).all()
        assert all(str(y.id) != str(yarn.id) for y in remaining)


# ---------------------------------------------------------------------------
# TestPurgeLoomsWithPhoto — loom deletion with photo_path storage cleanup
# ---------------------------------------------------------------------------


class TestPurgeLoomsWithPhoto:
    @pytest.mark.asyncio
    async def test_deletes_loom_with_photo_path(self, db_session, test_user, mock_engine_and_session):
        from sqlalchemy import select

        from app.models.loom import Loom

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor_loom",
            manufacturer="PhotoMaker",
            model_name="PhotoLoom",
            photo_path="looms/photo.jpg",
            deleted_at=_ago(days=30),
        )
        db_session.add(loom)
        await db_session.commit()

        result = await _purge(7)

        assert result["looms"] >= 1
        remaining = (await db_session.scalars(select(Loom))).all()
        assert all(str(lm.id) != str(loom.id) for lm in remaining)


# ---------------------------------------------------------------------------
# TestPurgeLoomsWithVersions — loom version attachment cleanup
# ---------------------------------------------------------------------------


class TestPurgeLoomsWithVersions:
    @pytest.mark.asyncio
    async def test_deletes_loom_versions_and_photos(self, db_session, test_user, mock_engine_and_session):
        from datetime import date

        from sqlalchemy import select

        from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor_loom",
            manufacturer="VersionMaker",
            model_name="VersionLoom",
            deleted_at=_ago(days=30),
        )
        db_session.add(loom)
        await db_session.flush()

        version = LoomVersion(
            id=uuid.uuid4(),
            loom_id=loom.id,
            version_number=1,
            effective_date=date.today(),
        )
        db_session.add(version)
        await db_session.flush()

        photo = LoomVersionPhoto(
            id=uuid.uuid4(),
            loom_version_id=version.id,
            filename="loom-photo.jpg",
            path="loom-versions/photo.jpg",
        )
        receipt = LoomVersionReceipt(
            id=uuid.uuid4(),
            loom_version_id=version.id,
            filename="receipt.pdf",
            path="loom-versions/receipt.pdf",
        )
        db_session.add(photo)
        db_session.add(receipt)
        await db_session.commit()

        result = await _purge(7)

        assert result["looms"] >= 1
        remaining_versions = (await db_session.scalars(select(LoomVersion))).all()
        assert all(str(v.id) != str(version.id) for v in remaining_versions)
        remaining_photos = (await db_session.scalars(select(LoomVersionPhoto))).all()
        assert all(str(p.id) != str(photo.id) for p in remaining_photos)
        remaining_receipts = (await db_session.scalars(select(LoomVersionReceipt))).all()
        assert all(str(r.id) != str(receipt.id) for r in remaining_receipts)
