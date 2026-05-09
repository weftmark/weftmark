"""Tests for SQLAlchemy pool observable gauges (app/metrics.py).

Uses a mock engine/pool so no real database connection is required.
Patches _meter with an InMemoryMetricReader-backed provider to assert
that each gauge callback reports the correct pool stat.
"""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.metrics as bm


def _make_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


def _get_gauge_value(reader: InMemoryMetricReader, metric_name: str) -> int | None:
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


class _MockPool:
    def __init__(self, size=5, checkedout=2, checkedin=3, overflow=-3):
        self._size = size
        self._checkedout = checkedout
        self._checkedin = checkedin
        self._overflow = overflow

    def size(self):
        return self._size

    def checkedout(self):
        return self._checkedout

    def checkedin(self):
        return self._checkedin

    def overflow(self):
        return self._overflow


class _MockEngine:
    def __init__(self, pool: _MockPool):
        class _SyncEngine:
            pass

        self.sync_engine = _SyncEngine()
        self.sync_engine.pool = pool


@pytest.fixture
def pool_metrics_reader():
    provider, reader = _make_provider()
    original_meter = bm._meter
    bm._meter = provider.get_meter("weftmark.business")
    yield reader
    bm._meter = original_meter
    provider.shutdown()


class TestPoolSizeGauge:
    def test_reports_configured_pool_size(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(size=5))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.size") == 5

    def test_reflects_different_pool_size(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(size=10))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.size") == 10


class TestPoolCheckedOutGauge:
    def test_reports_checked_out_connections(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(checkedout=3))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.checked_out") == 3

    def test_zero_when_no_active_queries(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(checkedout=0))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.checked_out") == 0


class TestPoolCheckedInGauge:
    def test_reports_idle_connections(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(checkedin=4))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.checked_in") == 4


class TestPoolOverflowGauge:
    def test_negative_overflow_means_unused_capacity(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(size=5, checkedout=0, overflow=-5))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.overflow") == -5

    def test_positive_overflow_means_pool_exhausted(self, pool_metrics_reader):
        engine = _MockEngine(_MockPool(size=5, checkedout=7, overflow=2))
        bm.register_pool_metrics(engine)

        assert _get_gauge_value(pool_metrics_reader, "weftmark.db.pool.overflow") == 2
