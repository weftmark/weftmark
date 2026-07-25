"""Tests for the Ravelry router and service — yarn-detail endpoint and auth guards."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
# TestImportYarnFromRavelry — app.services.ravelry.import_yarn_from_ravelry
# ---------------------------------------------------------------------------

_FULL_YARN_RESPONSE = {
    "yarn": {
        "id": 42,
        "name": "Cascade 220",
        "yarn_company": {"name": "Cascade Yarns", "url": "https://cascadeyarns.com"},
        "yarn_weight": {"name": "Worsted"},
        "fiber_content": "100% Peruvian Highland Wool",
        "permalink": "cascade-220",
        "discontinued": False,
        "machine_washable": False,
        "yardage": 220,
        "yarn_attributes": [{"id": 1, "name": "Machine Washable"}, {"name": "no-id-entry"}, {"id": 2}],
        "photos": [
            {"sort_order": 2, "medium_url": "https://x/med2.jpg", "square_url": "https://x/sq2.jpg"},
            {
                "sort_order": 1,
                "medium_url": "https://x/med1.jpg",
                "small_url": "https://x/small1.jpg",
                "square_url": "https://x/sq1.jpg",
                "thumbnail_url": "https://x/thumb1.jpg",
            },
        ],
    }
}

_MINIMAL_YARN_RESPONSE = {"yarn": {"id": 99}}


class TestImportYarnFromRavelry:
    async def test_full_data_creates_yarn_with_all_fields(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user
    ):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_FULL_YARN_RESPONSE),
        ):
            resp = await auth_client.post(
                "/api/ravelry/import-yarn",
                json={"ravelry_yarn_id": 42, "color_name": "Cobalt", "color_hex": "#0047AB"},
            )

        assert resp.status_code == 200
        yarn_id = resp.json()["id"]

        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == yarn_id))
        assert yarn.brand == "Cascade Yarns"
        assert yarn.name == "Cascade 220"
        assert yarn.color_name == "Cobalt"
        assert yarn.color_hex == "#0047AB"
        assert yarn.weight_category == "worsted"
        assert yarn.fiber_content == "100% Peruvian Highland Wool"
        assert yarn.ravelry_permalink == "cascade-220"
        assert yarn.ravelry_discontinued is False
        assert yarn.ravelry_yarn_company_url == "https://cascadeyarns.com"
        assert yarn.ravelry_yarn_id == 42
        assert yarn.owner_id == test_user.id

    async def test_unit_yardage_converted_to_decimal(self, auth_client: AsyncClient, db_session: AsyncSession):
        from decimal import Decimal

        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_FULL_YARN_RESPONSE),
        ):
            resp = await auth_client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 42})

        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == resp.json()["id"]))
        assert yarn.unit_yardage == Decimal("220")

    async def test_yarn_attribute_ids_filters_entries_without_id(
        self, auth_client: AsyncClient, db_session: AsyncSession
    ):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_FULL_YARN_RESPONSE),
        ):
            resp = await auth_client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 42})

        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == resp.json()["id"]))
        assert yarn.yarn_attribute_ids == [1, 2]

    async def test_photo_urls_use_lowest_sort_order_photo(self, auth_client: AsyncClient, db_session: AsyncSession):
        """Two photos with sort_order 2 and 1 — the sort_order=1 photo's URLs must win."""
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_FULL_YARN_RESPONSE),
        ):
            resp = await auth_client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 42})

        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == resp.json()["id"]))
        assert yarn.ravelry_photo_url == "https://x/med1.jpg"
        assert yarn.ravelry_thumbnail_url == "https://x/sq1.jpg"

    async def test_minimal_data_falls_back_to_unknown(self, auth_client: AsyncClient, db_session: AsyncSession):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_MINIMAL_YARN_RESPONSE),
        ):
            resp = await auth_client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 99})

        assert resp.status_code == 200
        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == resp.json()["id"]))
        assert yarn.brand == "Unknown"
        assert yarn.name == "Unknown"
        assert yarn.weight_category is None
        assert yarn.unit_yardage is None
        assert yarn.ravelry_photo_url is None
        assert yarn.ravelry_thumbnail_url is None
        assert yarn.yarn_attribute_ids == []

    async def test_empty_color_strings_stored_as_none(self, auth_client: AsyncClient, db_session: AsyncSession):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(return_value=_MINIMAL_YARN_RESPONSE),
        ):
            resp = await auth_client.post(
                "/api/ravelry/import-yarn",
                json={"ravelry_yarn_id": 99, "color_name": "", "color_hex": ""},
            )

        from sqlalchemy import select

        from app.models.yarn import Yarn

        yarn = await db_session.scalar(select(Yarn).where(Yarn.id == resp.json()["id"]))
        assert yarn.color_name is None
        assert yarn.color_hex is None

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 42})
        assert resp.status_code == 401

    async def test_returns_502_on_ravelry_error(self, auth_client: AsyncClient):
        with patch(
            "app.services.ravelry._basic_auth_get",
            new=AsyncMock(side_effect=RuntimeError("Ravelry API down")),
        ):
            resp = await auth_client.post("/api/ravelry/import-yarn", json={"ravelry_yarn_id": 42})
        assert resp.status_code == 502


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
