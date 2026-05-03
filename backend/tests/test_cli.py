"""Tests for the CLI seed command (app.cli)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cli import _clear_local, _poll_for_clerk_attach, cmd_seed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    s = MagicMock()
    s.app_env = "dev"
    s.seed_enabled = True
    s.clerk_secret_key = "sk_test_abcdefghij"
    s.database_url = "postgresql+asyncpg://user:pass@localhost/test"
    s.storage_backend = "local"
    s.upload_dir = "/tmp/test_uploads"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_session_factory():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.merge = AsyncMock()
    factory = MagicMock(return_value=session)
    return factory, session


def _make_engine():
    engine = MagicMock()
    engine.dispose = AsyncMock()
    return engine


# ---------------------------------------------------------------------------
# Precheck: app_env
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_not_dev(tmp_path):
    settings = _make_settings(app_env="prod")
    with patch("app.cli.get_settings", return_value=settings):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "seed.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: seed_enabled
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_seed_disabled(tmp_path):
    settings = _make_settings(seed_enabled=False)
    with patch("app.cli.get_settings", return_value=settings):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "seed.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: clerk_secret_key
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_no_clerk_key(tmp_path):
    settings = _make_settings(clerk_secret_key="")
    with patch("app.cli.get_settings", return_value=settings):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "seed.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: Clerk API unreachable
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_clerk_unreachable(tmp_path):
    settings = _make_settings()
    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(side_effect=Exception("connection refused"))),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "seed.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: Clerk has existing users — proceeds, does not abort
# ---------------------------------------------------------------------------


async def test_seed_proceeds_when_clerk_has_users(tmp_path):
    """Existing Clerk users are no longer a reason to abort — they get deleted."""
    settings = _make_settings()
    factory, _ = _make_session_factory()

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[{"id": "user_abc"}])),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
    ):
        # Should exit on missing config, not on Clerk having users
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "nonexistent.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: DB unreachable
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_db_unreachable(tmp_path):
    settings = _make_settings()
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.execute = AsyncMock(side_effect=Exception("db down"))
    factory = MagicMock(return_value=session)

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[])),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "seed.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: seed config missing
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_config_missing(tmp_path):
    settings = _make_settings()
    factory, _ = _make_session_factory()

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[])),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(tmp_path / "nonexistent.json"), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Precheck: seed config has no users
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_no_users_in_config(tmp_path):
    settings = _make_settings()
    factory, _ = _make_session_factory()
    config = tmp_path / "seed.json"
    config.write_text(json.dumps({"users": []}))

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[])),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(config), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Reset: Clerk deletion is called before Alembic
# ---------------------------------------------------------------------------


async def test_seed_deletes_clerk_users_before_alembic(tmp_path):
    """_clerk_delete_all_users must be called in the Reset phase."""
    settings = _make_settings()
    factory, session = _make_session_factory()
    config = tmp_path / "seed.json"
    config.write_text(json.dumps({"users": [{"email": "a@b.com", "username": "a", "role": "user"}]}))

    delete_mock = AsyncMock(return_value=3)
    pre_user = MagicMock()
    pre_user.id = uuid.uuid4()
    attached_user = MagicMock()
    attached_user.clerk_user_id = "user_new"

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[{"id": "u1"}, {"id": "u2"}, {"id": "u3"}])),
        patch("app.cli._clerk_delete_all_users", delete_mock),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
        patch("app.cli._alembic_reset"),
        patch("app.cli._clear_storage"),
        patch("app.cli._preregister_user", AsyncMock(return_value=pre_user)),
        patch("app.cli._clerk_create_user", AsyncMock(return_value={"id": "user_new"})),
        patch("app.cli._poll_for_clerk_attach", AsyncMock(return_value=attached_user)),
    ):
        await cmd_seed(str(config), 5)

    delete_mock.assert_awaited_once_with(settings.clerk_secret_key)


# ---------------------------------------------------------------------------
# Reset: Clerk deletion failure aborts
# ---------------------------------------------------------------------------


async def test_seed_aborts_when_clerk_delete_fails(tmp_path):
    settings = _make_settings()
    factory, _ = _make_session_factory()
    config = tmp_path / "seed.json"
    config.write_text(json.dumps({"users": [{"email": "a@b.com", "username": "a"}]}))

    with (
        patch("app.cli.get_settings", return_value=settings),
        patch("app.cli._clerk_list_users", AsyncMock(return_value=[])),
        patch("app.cli._clerk_delete_all_users", AsyncMock(side_effect=Exception("clerk error"))),
        patch("app.cli.create_async_engine", return_value=_make_engine()),
        patch("app.cli.async_sessionmaker", return_value=factory),
    ):
        with pytest.raises(SystemExit) as exc_info:
            await cmd_seed(str(config), 5)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _poll_for_clerk_attach — success
# ---------------------------------------------------------------------------


async def test_poll_for_clerk_attach_returns_user_when_attached():
    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.clerk_user_id = "user_abc123"

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.get = AsyncMock(return_value=mock_user)
    factory = MagicMock(return_value=session)

    result = await _poll_for_clerk_attach(factory, user_id, timeout=5)

    assert result is mock_user


# ---------------------------------------------------------------------------
# _poll_for_clerk_attach — timeout
# ---------------------------------------------------------------------------


async def test_poll_for_clerk_attach_raises_timeout_when_never_attached():
    user_id = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.clerk_user_id = None

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.get = AsyncMock(return_value=mock_user)
    factory = MagicMock(return_value=session)

    with pytest.raises(TimeoutError):
        await _poll_for_clerk_attach(factory, user_id, timeout=0)


# ---------------------------------------------------------------------------
# _clear_local — clears existing files
# ---------------------------------------------------------------------------


def test_clear_local_removes_existing_files(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / "image.jpg").write_bytes(b"fake-image")
    (upload_dir / "data.wif").write_bytes(b"fake-wif")

    settings = MagicMock()
    settings.upload_dir = str(upload_dir)

    _clear_local(settings)

    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# _clear_local — creates directory when it doesn't exist
# ---------------------------------------------------------------------------


def test_clear_local_creates_missing_directory(tmp_path):
    upload_dir = tmp_path / "new_uploads"
    assert not upload_dir.exists()

    settings = MagicMock()
    settings.upload_dir = str(upload_dir)

    _clear_local(settings)

    assert upload_dir.exists()
    assert upload_dir.is_dir()
