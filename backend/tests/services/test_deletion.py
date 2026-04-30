import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.deletion import initiate_user_deletion


class TestInitiateUserDeletion:
    async def _create_user(self, db_session: AsyncSession) -> User:
        user = User(
            email=f"todelete-{uuid.uuid4().hex[:6]}@test.com",
            display_name="To Delete",
            oidc_sub=f"todelete-sub-{uuid.uuid4().hex}",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    def _make_mocks(self):
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        mock_email = AsyncMock()
        return mock_task, mock_email

    async def test_sets_deletion_state_pending(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        assert user.deletion_state == "pending"

    async def test_sets_deleted_at(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        assert user.deleted_at is not None

    async def test_sets_deletion_initiated_at(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        assert user.deletion_initiated_at is not None
        assert isinstance(user.deletion_initiated_at, datetime)

    async def test_dispatches_celery_task(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        mock_task.delay.assert_called_once_with(str(user.id))

    async def test_notifies_admins_when_present(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        admin = User(
            email="notify-admin@del-test.com",
            display_name="Notify Admin",
            oidc_sub=f"notify-admin-sub-{uuid.uuid4().hex}",
            is_admin=True,
        )
        db_session.add(admin)
        await db_session.commit()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        mock_email.assert_called_once()
        called_emails = mock_email.call_args[0][0]
        assert admin.email in called_emails

    async def test_no_notification_when_no_admins(self, db_session: AsyncSession):
        mock_task, mock_email = self._make_mocks()
        user = await self._create_user(db_session)
        with (
            patch("app.tasks.deletion.run_user_deletion", mock_task),
            patch("app.services.email.send_deletion_created_admin", mock_email),
        ):
            await initiate_user_deletion(db_session, user)
        mock_email.assert_not_called()
