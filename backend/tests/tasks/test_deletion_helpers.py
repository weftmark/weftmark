"""Tests for app.tasks.deletion helper functions.

Kept separate from test_deletion_task.py because that file defines a local
mock_storage fixture that shadows the conftest autouse mock_storage and patches
_purge_storage for all tests in the file. These helpers need the real
_purge_storage, so they live here.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# TestSafeDelete — _safe_delete helper
# ---------------------------------------------------------------------------


class TestSafeDelete:
    def test_calls_storage_delete(self):
        from app.tasks.deletion import _safe_delete

        mock_storage = MagicMock()
        _safe_delete(mock_storage, "drafts/file.wif")
        mock_storage._delete.assert_called_once_with("drafts/file.wif")

    def test_swallows_exceptions(self):
        from app.tasks.deletion import _safe_delete

        mock_storage = MagicMock()
        mock_storage._delete.side_effect = Exception("storage gone")
        _safe_delete(mock_storage, "drafts/file.wif")  # must not raise


# ---------------------------------------------------------------------------
# TestGetAdminAndSuperuserEmails — DB query helpers
# ---------------------------------------------------------------------------


class TestGetAdminEmails:
    async def test_returns_admin_email(self, db_session, admin_user):
        from app.tasks.deletion import _get_admin_emails

        result = await _get_admin_emails(db_session)
        assert admin_user.email in result

    async def test_excludes_regular_user(self, db_session, test_user):
        from app.tasks.deletion import _get_admin_emails

        result = await _get_admin_emails(db_session)
        assert test_user.email not in result

    async def test_returns_list(self, db_session):
        from app.tasks.deletion import _get_admin_emails

        result = await _get_admin_emails(db_session)
        assert isinstance(result, list)


class TestGetSuperuserEmails:
    async def test_returns_superuser_email(self, db_session, superuser_user):
        from app.tasks.deletion import _get_superuser_emails

        result = await _get_superuser_emails(db_session)
        assert superuser_user.email in result

    async def test_excludes_regular_admin(self, db_session, admin_user):
        from app.tasks.deletion import _get_superuser_emails

        result = await _get_superuser_emails(db_session)
        assert admin_user.email not in result


# ---------------------------------------------------------------------------
# TestPurgeStorage — _purge_storage with real DB data
# ---------------------------------------------------------------------------


class TestPurgeStorage:
    async def test_no_data_runs_cleanly(self, db_session, test_user):
        from app.tasks.deletion import _purge_storage

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

    async def test_deletes_draft_wif_path(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.deletion import _purge_storage

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Storage Draft",
            wif_filename="storage.wif",
            wif_path="drafts/storage.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        mock_storage._delete.assert_any_call("drafts/storage.wif")

    async def test_deletes_draft_preview_path(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.deletion import _purge_storage

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Preview Storage Draft",
            wif_filename="pvstorage.wif",
            wif_path="drafts/pvstorage.wif",
            preview_path="previews/pvstorage.svg",
        )
        db_session.add(draft)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        called_paths = [c.args[0] for c in mock_storage._delete.call_args_list]
        assert "previews/pvstorage.svg" in called_paths

    async def test_deletes_yarn_photo(self, db_session, test_user):
        from app.models.yarn import Yarn
        from app.tasks.deletion import _purge_storage

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="TestBrand",
            name="TestYarn",
            photo_path="yarn-photos/test.jpg",
        )
        db_session.add(yarn)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        called_paths = [c.args[0] for c in mock_storage._delete.call_args_list]
        assert "yarn-photos/test.jpg" in called_paths

    async def test_deletes_loom_photo(self, db_session, test_user):
        from app.models.loom import Loom
        from app.tasks.deletion import _purge_storage

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor",
            manufacturer="Acme",
            model_name="TestLoom",
            photo_path="loom-photos/test.jpg",
        )
        db_session.add(loom)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        called_paths = [c.args[0] for c in mock_storage._delete.call_args_list]
        assert "loom-photos/test.jpg" in called_paths

    async def test_skips_yarn_without_photo(self, db_session, test_user):
        from app.models.yarn import Yarn
        from app.tasks.deletion import _purge_storage

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="NoPic",
            name="PlainYarn",
        )
        db_session.add(yarn)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)
        mock_storage._delete.assert_not_called()

    async def test_deletes_project_photo(self, db_session, test_user):
        from app.models.draft import Draft
        from app.models.project import Project, ProjectPhoto
        from app.tasks.deletion import _purge_storage

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Photo Draft",
            wif_filename="photo.wif",
            wif_path="drafts/photo.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Photo Project",
            project_type="treadle",
            total_picks=4,
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

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        called_paths = [c.args[0] for c in mock_storage._delete.call_args_list]
        assert "projects/photo.jpg" in called_paths

    async def test_delete_project_tiles_exception_swallowed(self, db_session, test_user):
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.deletion import _purge_storage

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Tiles Draft",
            wif_filename="tiles.wif",
            wif_path="drafts/tiles.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Tiles Project",
            project_type="treadle",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(side_effect=RuntimeError("s3 gone"))
        await _purge_storage(db_session, test_user.id, mock_storage)  # must not raise

    async def test_deletes_loom_version_photo_and_receipt(self, db_session, test_user):
        from datetime import date

        from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt
        from app.tasks.deletion import _purge_storage

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor",
            manufacturer="Acme",
            model_name="VersionedLoom",
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
            filename="loom.jpg",
            path="loom-versions/loom.jpg",
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

        mock_storage = MagicMock()
        mock_storage.delete_project_tiles = MagicMock(return_value=0)
        await _purge_storage(db_session, test_user.id, mock_storage)

        called_paths = [c.args[0] for c in mock_storage._delete.call_args_list]
        assert "loom-versions/loom.jpg" in called_paths
        assert "loom-versions/receipt.pdf" in called_paths


# ---------------------------------------------------------------------------
# TestNotifyHelpers — _notify_admins_complete / _notify_stalled
# ---------------------------------------------------------------------------


class TestNotifyAdminsComplete:
    async def test_calls_email_when_admins_exist(self, db_session, admin_user):
        from app.tasks.deletion import _notify_admins_complete

        with patch("app.services.email.send_deletion_completed_admin", new_callable=AsyncMock) as mock_email:
            await _notify_admins_complete(db_session, "user@example.com", "User Name")

        mock_email.assert_called_once()
        assert admin_user.email in mock_email.call_args[0][0]

    async def test_no_call_when_no_admins(self, db_session, test_user):
        from app.tasks.deletion import _notify_admins_complete

        with patch("app.services.email.send_deletion_completed_admin", new_callable=AsyncMock) as mock_email:
            await _notify_admins_complete(db_session, "user@example.com", "User Name")

        mock_email.assert_not_called()

    async def test_swallows_email_exception(self, db_session, admin_user):
        from app.tasks.deletion import _notify_admins_complete

        with patch(
            "app.services.email.send_deletion_completed_admin",
            new_callable=AsyncMock,
            side_effect=Exception("smtp error"),
        ):
            await _notify_admins_complete(db_session, "user@example.com", "User Name")


class TestNotifyStalled:
    async def test_calls_email_when_superusers_exist(self, db_session, superuser_user):
        from app.tasks.deletion import _notify_stalled

        with patch("app.services.email.send_deletion_stalled_superuser", new_callable=AsyncMock) as mock_email:
            await _notify_stalled(db_session, uuid.uuid4(), "user@example.com", "User Name")

        mock_email.assert_called_once()
        assert superuser_user.email in mock_email.call_args[0][0]

    async def test_no_call_when_no_superusers(self, db_session, test_user):
        from app.tasks.deletion import _notify_stalled

        with patch("app.services.email.send_deletion_stalled_superuser", new_callable=AsyncMock) as mock_email:
            await _notify_stalled(db_session, uuid.uuid4(), "user@example.com", "User Name")

        mock_email.assert_not_called()

    async def test_swallows_email_exception(self, db_session, superuser_user):
        from app.tasks.deletion import _notify_stalled

        with patch(
            "app.services.email.send_deletion_stalled_superuser",
            new_callable=AsyncMock,
            side_effect=Exception("smtp error"),
        ):
            await _notify_stalled(db_session, uuid.uuid4(), "user@example.com", "User Name")
