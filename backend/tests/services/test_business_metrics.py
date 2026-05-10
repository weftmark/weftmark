"""Tests for business metrics counters (app/metrics.py).

Each test patches the module-level counter with one backed by an
InMemoryMetricReader so we can assert the exact value and attributes
without a live OTel Collector.
"""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.metrics as bm
import app.routers.auth as auth_router


def _mock_request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers.get = lambda key, default="": headers.get(key, default)
    return req


def _make_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


def _get_data_points(reader: InMemoryMetricReader, metric_name: str) -> list:
    """Return all data points for the named metric across all scopes."""
    points = []
    for resource_metric in reader.get_metrics_data().resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == metric_name:
                    for dp in metric.data.data_points:
                        points.append(dp)
    return points


@pytest.fixture
def patched_metrics():
    """Replace all business counters with in-memory-backed equivalents."""
    provider, reader = _make_provider()
    meter = provider.get_meter("weftmark.business")

    originals = {
        "signups_total": bm.signups_total,
        "signups_approved_total": bm.signups_approved_total,
        "eula_accepted_total": bm.eula_accepted_total,
        "role_changes_total": bm.role_changes_total,
        "logins_total": bm.logins_total,
        "sessions_ended_total": bm.sessions_ended_total,
    }

    bm.signups_total = meter.create_counter("weftmark.user.signups", unit="1")
    bm.signups_approved_total = meter.create_counter("weftmark.user.signups_approved", unit="1")
    bm.eula_accepted_total = meter.create_counter("weftmark.user.eula_accepted", unit="1")
    bm.role_changes_total = meter.create_counter("weftmark.user.role_changes", unit="1")
    bm.logins_total = meter.create_counter("weftmark.user.logins", unit="1")
    bm.sessions_ended_total = meter.create_counter("weftmark.user.sessions_ended", unit="1")

    yield reader

    bm.signups_total = originals["signups_total"]
    bm.signups_approved_total = originals["signups_approved_total"]
    bm.eula_accepted_total = originals["eula_accepted_total"]
    bm.role_changes_total = originals["role_changes_total"]
    bm.logins_total = originals["logins_total"]
    bm.sessions_ended_total = originals["sessions_ended_total"]

    provider.shutdown()


class TestSignupsCounter:
    def test_pending_signup_increments_counter(self, patched_metrics):
        bm.signups_total.add(1, {"signup_type": "pending"})

        points = _get_data_points(patched_metrics, "weftmark.user.signups")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"signup_type": "pending"}

    def test_invited_signup_increments_counter(self, patched_metrics):
        bm.signups_total.add(1, {"signup_type": "invited"})

        points = _get_data_points(patched_metrics, "weftmark.user.signups")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"signup_type": "invited"}

    def test_multiple_signups_accumulate(self, patched_metrics):
        bm.signups_total.add(1, {"signup_type": "pending"})
        bm.signups_total.add(1, {"signup_type": "pending"})
        bm.signups_total.add(1, {"signup_type": "invited"})

        points = _get_data_points(patched_metrics, "weftmark.user.signups")
        by_type = {p.attributes["signup_type"]: p.value for p in points}
        assert by_type["pending"] == 2
        assert by_type["invited"] == 1


class TestSignupsApprovedCounter:
    def test_approval_increments_counter(self, patched_metrics):
        bm.signups_approved_total.add(1)

        points = _get_data_points(patched_metrics, "weftmark.user.signups_approved")
        assert len(points) == 1
        assert points[0].value == 1

    def test_multiple_approvals_accumulate(self, patched_metrics):
        bm.signups_approved_total.add(1)
        bm.signups_approved_total.add(1)

        points = _get_data_points(patched_metrics, "weftmark.user.signups_approved")
        assert points[0].value == 2


class TestEulaAcceptedCounter:
    def test_eula_acceptance_increments_counter(self, patched_metrics):
        bm.eula_accepted_total.add(1)

        points = _get_data_points(patched_metrics, "weftmark.user.eula_accepted")
        assert len(points) == 1
        assert points[0].value == 1

    def test_multiple_acceptances_accumulate(self, patched_metrics):
        bm.eula_accepted_total.add(1)
        bm.eula_accepted_total.add(1)
        bm.eula_accepted_total.add(1)

        points = _get_data_points(patched_metrics, "weftmark.user.eula_accepted")
        assert points[0].value == 3


class TestRoleChangesCounter:
    def test_promote_to_admin_increments_counter(self, patched_metrics):
        bm.role_changes_total.add(1, {"new_role": "admin"})

        points = _get_data_points(patched_metrics, "weftmark.user.role_changes")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"new_role": "admin"}

    def test_demote_to_user_increments_counter(self, patched_metrics):
        bm.role_changes_total.add(1, {"new_role": "user"})

        points = _get_data_points(patched_metrics, "weftmark.user.role_changes")
        assert len(points) == 1
        assert points[0].attributes == {"new_role": "user"}

    def test_multiple_role_changes_accumulate_by_role(self, patched_metrics):
        bm.role_changes_total.add(1, {"new_role": "admin"})
        bm.role_changes_total.add(1, {"new_role": "admin"})
        bm.role_changes_total.add(1, {"new_role": "user"})

        points = _get_data_points(patched_metrics, "weftmark.user.role_changes")
        by_role = {p.attributes["new_role"]: p.value for p in points}
        assert by_role["admin"] == 2
        assert by_role["user"] == 1


_SESSION_CREATED_DATA = {
    "id": "sess_test123",
    "user_id": "user_test123",
    "status": "active",
    "user": {
        "id": "user_test123",
        "public_metadata": {"is_admin": False, "status": "active"},
    },
}


class TestLoginsCounter:
    @pytest.mark.asyncio
    async def test_user_login_increments_counter(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        await auth_router._handle_session_created(_SESSION_CREATED_DATA)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"role": "user"}

    @pytest.mark.asyncio
    async def test_admin_login_uses_admin_role_attribute(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        data = {**_SESSION_CREATED_DATA, "user": {"id": "user_test123", "public_metadata": {"is_admin": True}}}
        await auth_router._handle_session_created(data)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert len(points) == 1
        assert points[0].attributes == {"role": "admin"}

    @pytest.mark.asyncio
    async def test_missing_public_metadata_defaults_to_user(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        data = {**_SESSION_CREATED_DATA, "user": {"id": "user_test123"}}
        await auth_router._handle_session_created(data)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert points[0].attributes == {"role": "user"}

    @pytest.mark.asyncio
    async def test_multiple_logins_accumulate_by_role(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        admin_data = {**_SESSION_CREATED_DATA, "user": {"id": "u1", "public_metadata": {"is_admin": True}}}
        await auth_router._handle_session_created(_SESSION_CREATED_DATA)
        await auth_router._handle_session_created(_SESSION_CREATED_DATA)
        await auth_router._handle_session_created(admin_data)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        by_role = {p.attributes["role"]: p.value for p in points}
        assert by_role["user"] == 2
        assert by_role["admin"] == 1


_GEO_FULL = {"country_iso": "US", "subdivision": "CO", "city": "Denver"}
_GEO_COUNTRY_ONLY = {"country_iso": "DE", "subdivision": "", "city": ""}


class TestLoginsGeoAttributes:
    @pytest.mark.asyncio
    async def test_no_request_emits_no_geo(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        await auth_router._handle_session_created(_SESSION_CREATED_DATA)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert points[0].attributes == {"role": "user"}

    @pytest.mark.asyncio
    async def test_mmdb_provides_full_geo(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        req = _mock_request({"CF-Connecting-IP": "203.0.113.42", "CF-IPCountry": "US"})

        with patch("app.services.geo.get_geo", return_value=_GEO_FULL):
            await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        attrs = points[0].attributes
        assert attrs["country"] == "US"
        assert attrs["subdivision"] == "CO"
        assert attrs["city"] == "Denver"

    @pytest.mark.asyncio
    async def test_mmdb_absent_falls_back_to_cf_ipcountry(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        req = _mock_request({"CF-Connecting-IP": "203.0.113.42", "CF-IPCountry": "GB"})

        with patch("app.services.geo.get_geo", return_value={}):
            await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        attrs = points[0].attributes
        assert attrs["country"] == "GB"
        assert "subdivision" not in attrs
        assert "city" not in attrs

    @pytest.mark.asyncio
    async def test_no_ip_no_mmdb_uses_cf_ipcountry(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        req = _mock_request({"CF-IPCountry": "FR"})

        await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert points[0].attributes == {"role": "user", "country": "FR"}

    @pytest.mark.asyncio
    async def test_empty_cf_ipcountry_omits_country_attribute(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        req = _mock_request({"CF-IPCountry": ""})

        await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert "country" not in points[0].attributes

    @pytest.mark.asyncio
    async def test_mmdb_country_iso_takes_precedence_over_cf_header(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        # CF says CA, MMDB says US — MMDB wins
        req = _mock_request({"CF-Connecting-IP": "203.0.113.42", "CF-IPCountry": "CA"})

        with patch("app.services.geo.get_geo", return_value=_GEO_FULL):
            await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        assert points[0].attributes["country"] == "US"

    @pytest.mark.asyncio
    async def test_mmdb_empty_subdivision_and_city_omitted(self, patched_metrics):
        auth_router.logins_total = bm.logins_total
        req = _mock_request({"CF-Connecting-IP": "203.0.113.42", "CF-IPCountry": "DE"})

        with patch("app.services.geo.get_geo", return_value=_GEO_COUNTRY_ONLY):
            await auth_router._handle_session_created(_SESSION_CREATED_DATA, req)

        points = _get_data_points(patched_metrics, "weftmark.user.logins")
        attrs = points[0].attributes
        assert attrs["country"] == "DE"
        assert "subdivision" not in attrs
        assert "city" not in attrs


_SESSION_ENDED_DATA = {
    "id": "sess_ended123",
    "user_id": "user_test123",
    "status": "ended",
    "user": {
        "id": "user_test123",
        "public_metadata": {"is_admin": False, "status": "active"},
    },
}


class TestSessionsEndedCounter:
    @pytest.mark.asyncio
    async def test_user_session_ended_increments_counter(self, patched_metrics):
        auth_router.sessions_ended_total = bm.sessions_ended_total
        await auth_router._handle_session_ended(_SESSION_ENDED_DATA)

        points = _get_data_points(patched_metrics, "weftmark.user.sessions_ended")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"role": "user"}

    @pytest.mark.asyncio
    async def test_admin_session_ended_uses_admin_role_attribute(self, patched_metrics):
        auth_router.sessions_ended_total = bm.sessions_ended_total
        data = {**_SESSION_ENDED_DATA, "user": {"id": "user_test123", "public_metadata": {"is_admin": True}}}
        await auth_router._handle_session_ended(data)

        points = _get_data_points(patched_metrics, "weftmark.user.sessions_ended")
        assert len(points) == 1
        assert points[0].attributes == {"role": "admin"}

    @pytest.mark.asyncio
    async def test_missing_public_metadata_defaults_to_user(self, patched_metrics):
        auth_router.sessions_ended_total = bm.sessions_ended_total
        data = {**_SESSION_ENDED_DATA, "user": {"id": "user_test123"}}
        await auth_router._handle_session_ended(data)

        points = _get_data_points(patched_metrics, "weftmark.user.sessions_ended")
        assert points[0].attributes == {"role": "user"}

    @pytest.mark.asyncio
    async def test_multiple_sessions_ended_accumulate_by_role(self, patched_metrics):
        auth_router.sessions_ended_total = bm.sessions_ended_total
        admin_data = {**_SESSION_ENDED_DATA, "user": {"id": "u1", "public_metadata": {"is_admin": True}}}
        await auth_router._handle_session_ended(_SESSION_ENDED_DATA)
        await auth_router._handle_session_ended(_SESSION_ENDED_DATA)
        await auth_router._handle_session_ended(admin_data)

        points = _get_data_points(patched_metrics, "weftmark.user.sessions_ended")
        by_role = {p.attributes["role"]: p.value for p in points}
        assert by_role["user"] == 2
        assert by_role["admin"] == 1
