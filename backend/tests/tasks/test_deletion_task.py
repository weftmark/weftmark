"""Tests for app.tasks.deletion._delete_user — the async core of the cascade task.

We call _delete_user directly rather than through run_user_deletion so we can
run it in the test event loop.  create_async_engine and sessionmaker are patched
so the task uses the test db_session instead of opening its own connection.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.loom import Loom
from app.models.user import User
from app.models.yarn import Yarn
from app.tasks.deletion import _delete_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_mock(retries: int = 0, max_retries: int = 3) -> MagicMock:
    t = MagicMock()
    t.request = MagicMock()
    t.request.retries = retries
    t.max_retries = max_retries
    return t


def _session_factory(db: AsyncSession):
    """Return a sessionmaker-compatible callable that yields db as the session."""

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass

    class _Factory:
        def __call__(self):
            return _Ctx()

    return _Factory()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db(db_session: AsyncSession):
    """Patch engine/session creation so _delete_user runs against db_session."""
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("app.tasks.deletion.create_async_engine", return_value=fake_engine),
        patch("app.tasks.deletion.sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield


@pytest.fixture()
def mock_storage():
    with patch("app.tasks.deletion._purge_storage", new_callable=AsyncMock):
        yield


@pytest.fixture()
def mock_emails():
    with (
        patch("app.services.email.send_deletion_completed_admin", new_callable=AsyncMock),
        patch("app.services.email.send_deletion_stalled_superuser", new_callable=AsyncMock),
    ):
        yield


# ---------------------------------------------------------------------------
# TestDeleteUserHappyPath
# ---------------------------------------------------------------------------


class TestDeleteUserHappyPath:
    async def _pending_user(self, db: AsyncSession) -> User:
        user = User(
            email=f"cascade-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Cascade User",
            oidc_sub=f"cascade-sub-{uuid.uuid4().hex}",
            deletion_state="pending",
        )
        user.soft_delete()
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def test_sets_state_complete(self, db_session, mock_db, mock_storage, mock_emails):
        user = await self._pending_user(db_session)
        await _delete_user(_task_mock(), user.id)
        await db_session.refresh(user)
        assert user.deletion_state == "complete"

    async def test_deletes_drafts(self, db_session, mock_db, mock_storage, mock_emails):
        user = await self._pending_user(db_session)
        db_session.add(Draft(owner_id=user.id, name="P", wif_filename="p.wif", wif_path="p/p.wif"))
        await db_session.commit()

        await _delete_user(_task_mock(), user.id)

        assert await db_session.scalar(select(Draft).where(Draft.owner_id == user.id)) is None

    async def test_deletes_yarn(self, db_session, mock_db, mock_storage, mock_emails):
        user = await self._pending_user(db_session)
        db_session.add(Yarn(owner_id=user.id, brand="B", name="Y"))
        await db_session.commit()

        await _delete_user(_task_mock(), user.id)

        assert await db_session.scalar(select(Yarn).where(Yarn.owner_id == user.id)) is None

    async def test_deletes_looms(self, db_session, mock_db, mock_storage, mock_emails):
        user = await self._pending_user(db_session)
        db_session.add(Loom(owner_id=user.id, loom_type="floor", manufacturer="Acme", model_name="L"))
        await db_session.commit()

        await _delete_user(_task_mock(), user.id)

        assert await db_session.scalar(select(Loom).where(Loom.owner_id == user.id)) is None

    async def test_deletes_pending_signup_for_clerk_user_id(self, db_session, mock_db, mock_storage, mock_emails):
        from sqlalchemy import select

        from app.models.pending_signup import PendingSignup

        clerk_id = f"clerk_{uuid.uuid4().hex[:12]}"
        user = User(
            email=f"clerk-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Clerk User",
            oidc_sub=f"clerk-sub-{uuid.uuid4().hex}",
            clerk_user_id=clerk_id,
            deletion_state="pending",
        )
        user.soft_delete()
        db_session.add(user)
        await db_session.flush()

        signup = PendingSignup(
            clerk_user_id=clerk_id,
            email="clerk-pending@test.com",
            display_name="Pending",
        )
        db_session.add(signup)
        await db_session.commit()
        await db_session.refresh(user)

        await _delete_user(_task_mock(), user.id)

        remaining = (await db_session.scalars(select(PendingSignup))).all()
        assert all(s.clerk_user_id != clerk_id for s in remaining)

    async def test_notifies_admins_on_complete(self, db_session, mock_db, mock_storage):
        admin = User(
            email="task-notify-admin@test.com",
            display_name="Task Admin",
            oidc_sub=f"task-admin-{uuid.uuid4().hex}",
            is_admin=True,
        )
        db_session.add(admin)
        await db_session.commit()

        user = await self._pending_user(db_session)

        with (
            patch("app.services.email.send_deletion_completed_admin", new_callable=AsyncMock) as mock_email,
            patch("app.services.email.send_deletion_stalled_superuser", new_callable=AsyncMock),
        ):
            await _delete_user(_task_mock(), user.id)

        mock_email.assert_called_once()
        assert admin.email in mock_email.call_args[0][0]


# ---------------------------------------------------------------------------
# TestDeleteUserSkipPaths
# ---------------------------------------------------------------------------


class TestDeleteUserSkipPaths:
    async def test_skips_not_found(self, db_session, mock_db, mock_storage, mock_emails):
        await _delete_user(_task_mock(), uuid.uuid4())

    async def test_skips_already_complete(self, db_session, mock_db, mock_storage, mock_emails):
        user = User(
            email=f"done-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Done",
            oidc_sub=f"done-{uuid.uuid4().hex}",
            deletion_state="complete",
        )
        user.soft_delete()
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        await _delete_user(_task_mock(), user.id)

        await db_session.refresh(user)
        assert user.deletion_state == "complete"


# ---------------------------------------------------------------------------
# TestDeleteUserErrorPaths
# ---------------------------------------------------------------------------


class TestDeleteUserErrorPaths:
    async def _pending_user(self, db: AsyncSession) -> User:
        user = User(
            email=f"err-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Error User",
            oidc_sub=f"err-sub-{uuid.uuid4().hex}",
            deletion_state="pending",
        )
        user.soft_delete()
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def test_soft_time_limit_sets_stalled(self, db_session, mock_db, mock_emails):
        user = await self._pending_user(db_session)

        with patch(
            "app.tasks.deletion._purge_storage",
            new_callable=AsyncMock,
            side_effect=SoftTimeLimitExceeded(),
        ):
            with pytest.raises(SoftTimeLimitExceeded):
                await _delete_user(_task_mock(), user.id)

        await db_session.refresh(user)
        assert user.deletion_state == "stalled"

    async def test_exception_at_max_retries_sets_stalled(self, db_session, mock_db, mock_emails):
        user = await self._pending_user(db_session)
        task = _task_mock(retries=3, max_retries=3)

        with patch(
            "app.tasks.deletion._purge_storage",
            new_callable=AsyncMock,
            side_effect=RuntimeError("storage error"),
        ):
            await _delete_user(task, user.id)

        await db_session.refresh(user)
        assert user.deletion_state == "stalled"

    async def test_exception_under_max_retries_calls_retry(self, db_session, mock_db, mock_emails):
        user = await self._pending_user(db_session)
        task = _task_mock(retries=0, max_retries=3)
        task.retry = MagicMock(side_effect=RuntimeError("retry scheduled"))

        with patch(
            "app.tasks.deletion._purge_storage",
            new_callable=AsyncMock,
            side_effect=RuntimeError("storage error"),
        ):
            with pytest.raises(RuntimeError, match="retry scheduled"):
                await _delete_user(task, user.id)

        task.retry.assert_called_once()

    def test_run_user_deletion_calls_asyncio_run(self):
        from app.tasks.deletion import run_user_deletion

        user_id = str(uuid.uuid4())
        with patch("app.tasks.deletion.asyncio") as mock_asyncio:
            mock_asyncio.run = MagicMock()
            run_user_deletion.run(user_id)
        mock_asyncio.run.assert_called_once()

    async def test_stalled_notifies_superusers(self, db_session, mock_db):
        superuser = User(
            email="stall-super@test.com",
            display_name="Stall Super",
            oidc_sub=f"stall-super-{uuid.uuid4().hex}",
            is_superuser=True,
        )
        db_session.add(superuser)
        await db_session.commit()

        user = await self._pending_user(db_session)

        with (
            patch(
                "app.tasks.deletion._purge_storage",
                new_callable=AsyncMock,
                side_effect=SoftTimeLimitExceeded(),
            ),
            patch("app.services.email.send_deletion_completed_admin", new_callable=AsyncMock),
            patch("app.services.email.send_deletion_stalled_superuser", new_callable=AsyncMock) as mock_stall_email,
        ):
            with pytest.raises(SoftTimeLimitExceeded):
                await _delete_user(_task_mock(), user.id)

        mock_stall_email.assert_called_once()
        assert superuser.email in mock_stall_email.call_args[0][0]
