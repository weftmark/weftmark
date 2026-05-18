"""Tests for app.services.clerk — Clerk management API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _clerk_user(uid="user_123", email="user@example.com", first="Test", last="User"):
    return {
        "id": uid,
        "email_addresses": [{"email_address": email}],
        "first_name": first,
        "last_name": last,
    }


def _mock_client(method: str, response: MagicMock):
    """Return a context-manager-compatible AsyncMock wired to return response."""
    client = AsyncMock()
    getattr(client, method).return_value = response
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx, client


def _ok_response(body: dict | list):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = body
    r.raise_for_status = MagicMock()
    return r


# ---------------------------------------------------------------------------
# TestParseClerkUser — internal helper (imported directly)
# ---------------------------------------------------------------------------


class TestParseClerkUser:
    def test_parses_id_email_display_name(self):
        from app.services.clerk import _parse_clerk_user

        result = _parse_clerk_user(_clerk_user())
        assert result["id"] == "user_123"
        assert result["email"] == "user@example.com"
        assert result["display_name"] == "Test User"

    def test_falls_back_to_email_when_no_name(self):
        from app.services.clerk import _parse_clerk_user

        u = _clerk_user(first="", last="")
        result = _parse_clerk_user(u)
        assert result["display_name"] == u["email_addresses"][0]["email_address"]

    def test_handles_empty_email_addresses(self):
        from app.services.clerk import _parse_clerk_user

        u = {"id": "u1", "email_addresses": [], "first_name": "A", "last_name": "B"}
        result = _parse_clerk_user(u)
        assert result["email"] == ""
        assert result["display_name"] == "A B"


# ---------------------------------------------------------------------------
# TestGetClerkUser
# ---------------------------------------------------------------------------


class TestGetClerkUser:
    async def test_returns_user_dict_on_200(self):
        from app.services.clerk import get_clerk_user

        response = _ok_response(_clerk_user())
        ctx, client = _mock_client("get", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_clerk_user("user_123")

        assert result is not None
        assert result["id"] == "user_123"
        assert result["email"] == "user@example.com"

    async def test_returns_none_on_404(self):
        from app.services.clerk import get_clerk_user

        response = MagicMock()
        response.status_code = 404
        ctx, client = _mock_client("get", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_clerk_user("missing_user")

        assert result is None

    async def test_returns_none_on_exception(self):
        from app.services.clerk import get_clerk_user

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await get_clerk_user("user_123")

        assert result is None

    async def test_calls_correct_endpoint(self):
        from app.services.clerk import get_clerk_user

        response = _ok_response(_clerk_user())
        ctx, client = _mock_client("get", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            await get_clerk_user("user_abc")

        call_url = client.get.call_args[0][0]
        assert "user_abc" in call_url


# ---------------------------------------------------------------------------
# TestListClerkUsers
# ---------------------------------------------------------------------------


class TestListClerkUsers:
    async def test_returns_list_of_user_dicts(self):
        from app.services.clerk import list_clerk_users

        batch = [_clerk_user("u1", "a@x.com"), _clerk_user("u2", "b@x.com")]
        response = _ok_response(batch)
        ctx, client = _mock_client("get", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await list_clerk_users()

        assert len(result) == 2
        assert result[0]["id"] == "u1"

    async def test_paginates_until_partial_batch(self):
        from app.services.clerk import list_clerk_users

        # First call returns 500 items (full batch), second returns 1 (stop)
        full_batch = [_clerk_user(f"u{i}", f"u{i}@x.com") for i in range(500)]
        partial_batch = [_clerk_user("u500", "u500@x.com")]

        responses = [_ok_response(full_batch), _ok_response(partial_batch)]
        client = AsyncMock()
        client.get.side_effect = responses
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=ctx):
            result = await list_clerk_users()

        assert len(result) == 501
        assert client.get.call_count == 2

    async def test_returns_empty_list_when_no_users(self):
        from app.services.clerk import list_clerk_users

        response = _ok_response([])
        ctx, client = _mock_client("get", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            result = await list_clerk_users()

        assert result == []


# ---------------------------------------------------------------------------
# TestSetUserMetadata
# ---------------------------------------------------------------------------


class TestSetUserMetadata:
    async def test_calls_patch_endpoint(self):
        from app.services.clerk import set_user_metadata

        response = MagicMock()
        response.raise_for_status = MagicMock()
        ctx, client = _mock_client("patch", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            await set_user_metadata("user_abc", {"approved": True})

        assert client.patch.called
        call_url = client.patch.call_args[0][0]
        assert "user_abc" in call_url

    async def test_swallows_exception_on_failure(self):
        from app.services.clerk import set_user_metadata

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("timeout"))
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=ctx):
            await set_user_metadata("user_abc", {"approved": True})  # must not raise


# ---------------------------------------------------------------------------
# TestBanClerkUser / TestUnbanClerkUser
# ---------------------------------------------------------------------------


class TestBanClerkUser:
    async def test_calls_ban_endpoint(self):
        from app.services.clerk import ban_clerk_user

        response = MagicMock()
        response.raise_for_status = MagicMock()
        ctx, client = _mock_client("post", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            await ban_clerk_user("user_abc")

        call_url = client.post.call_args[0][0]
        assert "user_abc" in call_url
        assert "ban" in call_url

    async def test_raises_on_http_error(self):
        from app.services.clerk import ban_clerk_user

        response = MagicMock()
        response.raise_for_status.side_effect = Exception("403 Forbidden")
        ctx, client = _mock_client("post", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            with pytest.raises(Exception):
                await ban_clerk_user("user_abc")


class TestUnbanClerkUser:
    async def test_calls_unban_endpoint(self):
        from app.services.clerk import unban_clerk_user

        response = MagicMock()
        response.raise_for_status = MagicMock()
        ctx, client = _mock_client("post", response)
        with patch("httpx.AsyncClient", return_value=ctx):
            await unban_clerk_user("user_abc")

        call_url = client.post.call_args[0][0]
        assert "user_abc" in call_url
        assert "unban" in call_url
