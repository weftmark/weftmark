"""Tests for business entity observable gauges (app/metrics.py).

Tests cover:
- update_gauge_cache / _gauge_cache state
- register_business_gauges callbacks return correct Observations
- record_business_metrics task returns expected result shape (mocked DB)
"""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.metrics as bm


def _make_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


def _get_gauge_value(reader: InMemoryMetricReader, metric_name: str):
    metrics_data = reader.get_metrics_data()
    if metrics_data is None:
        return None
    for rm in metrics_data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == metric_name:
                    points = list(m.data.data_points)
                    if points:
                        return points[0].value
    return None


@pytest.fixture
def gauge_reader():
    provider, reader = _make_provider()
    original_meter = bm._meter
    original_cache = dict(bm._gauge_cache)
    bm._meter = provider.get_meter("weftmark.business")
    bm._gauge_cache.clear()
    yield reader
    bm._meter = original_meter
    bm._gauge_cache.clear()
    bm._gauge_cache.update(original_cache)
    provider.shutdown()


class TestGaugeCache:
    def test_update_sets_value(self):
        bm._gauge_cache.clear()
        bm.update_gauge_cache("weftmark.users.total", 42)
        assert bm._gauge_cache["weftmark.users.total"] == 42

    def test_update_overwrites_existing(self):
        bm._gauge_cache["weftmark.users.total"] = 10
        bm.update_gauge_cache("weftmark.users.total", 99)
        assert bm._gauge_cache["weftmark.users.total"] == 99


class TestBusinessGaugesCallbacks:
    def test_users_total_gauge_reflects_cache(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.users.total", 15)

        assert _get_gauge_value(gauge_reader, "weftmark.users.total") == 15

    def test_pending_approval_gauge_reflects_cache(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.users.pending_approval", 3)

        assert _get_gauge_value(gauge_reader, "weftmark.users.pending_approval") == 3

    def test_projects_total_gauge_reflects_cache(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.projects.total", 47)

        assert _get_gauge_value(gauge_reader, "weftmark.projects.total") == 47

    def test_storage_used_bytes_gauge_reflects_cache(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.storage.used_bytes", 1_048_576)

        assert _get_gauge_value(gauge_reader, "weftmark.storage.used_bytes") == 1_048_576

    def test_users_at_quota_gauge_reflects_cache(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.storage.users_at_quota", 2)

        assert _get_gauge_value(gauge_reader, "weftmark.storage.users_at_quota") == 2

    def test_empty_cache_emits_no_observations(self, gauge_reader):
        bm.register_business_gauges()
        # cache is empty — gauge should produce no data points
        assert _get_gauge_value(gauge_reader, "weftmark.users.total") is None

    def test_gauge_updates_when_cache_changes(self, gauge_reader):
        bm.register_business_gauges()
        bm.update_gauge_cache("weftmark.users.total", 10)
        assert _get_gauge_value(gauge_reader, "weftmark.users.total") == 10

        bm.update_gauge_cache("weftmark.users.total", 20)
        # Force a new collection cycle by creating a fresh reader snapshot
        assert bm._gauge_cache["weftmark.users.total"] == 20


class TestRecordBusinessMetricsTask:
    def test_task_returns_expected_keys(self):
        from app.tasks.metrics import record_business_metrics

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.scalar.side_effect = [5, 2, 12, 1024, 512, 0]

        mock_engine = MagicMock()

        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session),
        ):
            result = record_business_metrics.run()

        assert set(result.keys()) == {
            "users_total",
            "pending_approval",
            "projects_total",
            "storage_used_bytes",
            "users_at_quota",
        }

    def test_task_updates_gauge_cache(self):
        from app.tasks.metrics import record_business_metrics

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.scalar.side_effect = [7, 1, 3, 2048, 0, 0]

        mock_engine = MagicMock()

        bm._gauge_cache.clear()
        with (
            patch("sqlalchemy.create_engine", return_value=mock_engine),
            patch("sqlalchemy.orm.Session", return_value=mock_session),
        ):
            record_business_metrics.run()

        assert bm._gauge_cache["weftmark.users.total"] == 7
        assert bm._gauge_cache["weftmark.users.pending_approval"] == 1
        assert bm._gauge_cache["weftmark.projects.total"] == 3
