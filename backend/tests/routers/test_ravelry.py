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
