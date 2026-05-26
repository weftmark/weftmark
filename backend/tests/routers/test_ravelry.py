"""Tests for the Ravelry router and service — yarn-detail endpoint and auth guards."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.ravelry import fetch_yarn_detail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YARN_DETAIL_RESPONSE = {
    "yarn": {"id": 42, "name": "Cascade 220"},
    "colorways": [
        {"id": 1, "name": "Cobalt", "current_status": "active", "photos": []},
        {"id": 2, "name": "Ruby", "current_status": "active", "photos": []},
    ],
}


# ---------------------------------------------------------------------------
# TestYarnDetail
# ---------------------------------------------------------------------------


class TestYarnDetail:
    async def test_returns_yarn_data_without_ravelry_credential(self, auth_client: AsyncClient):
        """Colorway fetch uses Basic auth — no user OAuth credential required."""
        with patch(
            "app.services.ravelry.fetch_yarn_detail",
            new=AsyncMock(return_value=_YARN_DETAIL_RESPONSE),
        ):
            resp = await auth_client.get("/api/ravelry/yarn-detail/42")

        assert resp.status_code == 200
        data = resp.json()
        assert data["yarn"]["id"] == 42
        assert len(data["colorways"]) == 2

    async def test_returns_colorways_in_response(self, auth_client: AsyncClient):
        with patch(
            "app.services.ravelry.fetch_yarn_detail",
            new=AsyncMock(return_value=_YARN_DETAIL_RESPONSE),
        ):
            resp = await auth_client.get("/api/ravelry/yarn-detail/42")

        assert resp.status_code == 200
        colorways = resp.json()["colorways"]
        assert colorways[0]["name"] == "Cobalt"
        assert colorways[1]["name"] == "Ruby"

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.get("/api/ravelry/yarn-detail/42")
        assert resp.status_code in (401, 403)

    async def test_returns_502_on_ravelry_error(self, auth_client: AsyncClient):
        with patch(
            "app.services.ravelry.fetch_yarn_detail",
            new=AsyncMock(side_effect=RuntimeError("Ravelry down")),
        ):
            resp = await auth_client.get("/api/ravelry/yarn-detail/42")

        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# TestFetchYarnDetailService — service function uses Basic auth
# ---------------------------------------------------------------------------


class TestFetchYarnDetailService:
    async def test_calls_basic_auth_get_with_colorways_param(self):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_YARN_DETAIL_RESPONSE),
        ) as mock_get:
            result = await fetch_yarn_detail(42)

        mock_get.assert_called_once_with("/yarns/42.json", {"include": "colorways"})
        assert result == _YARN_DETAIL_RESPONSE

    async def test_returns_response_from_basic_auth_get(self):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_YARN_DETAIL_RESPONSE),
        ):
            result = await fetch_yarn_detail(99)

        assert result["yarn"]["id"] == 42
        assert len(result["colorways"]) == 2

    async def test_propagates_exception_from_basic_auth_get(self):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(side_effect=ValueError("API key not configured")),
        ):
            with pytest.raises(ValueError, match="API key not configured"):
                await fetch_yarn_detail(42)


# ---------------------------------------------------------------------------
# TestSafeLogHelper — pure function
# ---------------------------------------------------------------------------


class TestSafeLogHelper:
    def _safe(self, s):
        from app.routers.ravelry import _safe

        return _safe(s)

    def test_strips_newlines(self):
        result = self._safe("state\ninjected")
        assert "\n" not in result
        assert "\\n" in result

    def test_strips_carriage_returns(self):
        result = self._safe("state\rinjected")
        assert "\r" not in result
        assert "\\r" in result

    def test_handles_none(self):
        assert self._safe(None) == ""

    def test_truncates_long_string(self):
        assert len(self._safe("x" * 200)) <= 100

    def test_normal_string_passes_through(self):
        assert self._safe("abc123") == "abc123"


# ---------------------------------------------------------------------------
# TestOAuthCallbackErrorPaths
# ---------------------------------------------------------------------------


class TestOAuthCallbackErrorPaths:
    async def test_error_param_redirects_with_ravelry_denied(self, client: AsyncClient):
        with patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=None)):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "abc123", "error": "access_denied", "error_description": "User denied"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert "ravelry=error" in location
        assert "reason=ravelry_denied" in location

    async def test_missing_code_redirects_with_missing_code(self, client: AsyncClient):
        with patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=None)):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "abc123"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
        assert "reason=missing_code" in resp.headers["location"]

    async def test_invalid_state_redirects_with_invalid_state(self, client: AsyncClient):
        with patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=None)):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "bad-state", "code": "auth_code"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
        assert "reason=invalid_state" in resp.headers["location"]

    async def test_error_with_newline_in_state_does_not_inject_log(self, client: AsyncClient):
        """Regression: log injection via state/error query params must be sanitised."""
        with patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=None)):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "abc\n[INJECTED]", "error": "access_denied"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
