"""Tests for Celery task outcome counters (app/celery_app.py signal handlers).

Calls the signal handler functions directly with a mock sender and patches
app.metrics.celery_tasks_total with an InMemoryMetricReader-backed counter
so assertions work without a live OTel Collector or Celery broker.
"""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.celery_app as ca
import app.metrics as bm


def _make_provider():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    return provider, reader


def _get_data_points(reader: InMemoryMetricReader, metric_name: str) -> list:
    points = []
    metrics_data = reader.get_metrics_data()
    if metrics_data is None:
        return points
    for rm in metrics_data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == metric_name:
                    for dp in m.data.data_points:
                        points.append(dp)
    return points


class _MockTask:
    """Minimal Celery task stub — only .name is needed."""

    def __init__(self, name: str):
        self.name = name


@pytest.fixture
def patched_celery_metrics():
    provider, reader = _make_provider()
    meter = provider.get_meter("weftmark.business")
    original = bm.celery_tasks_total
    bm.celery_tasks_total = meter.create_counter("weftmark.celery.tasks", unit="1")
    yield reader
    bm.celery_tasks_total = original
    provider.shutdown()


class TestCeleryTasksSucceeded:
    def test_success_increments_counter(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.preview.render_preview")
        ca._on_task_postrun(task_id="t1", state="SUCCESS", sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert len(points) == 1
        assert points[0].value == 1
        assert points[0].attributes == {"state": "succeeded", "task": "app.tasks.preview.render_preview"}

    def test_non_success_state_does_not_increment(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.preview.render_preview")
        ca._on_task_postrun(task_id="t1", state="FAILURE", sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert len(points) == 0

    def test_multiple_successes_accumulate_by_task(self, patched_celery_metrics):
        ca._on_task_postrun(task_id="t1", state="SUCCESS", sender=_MockTask("app.tasks.preview.render_preview"))
        ca._on_task_postrun(task_id="t2", state="SUCCESS", sender=_MockTask("app.tasks.preview.render_preview"))
        ca._on_task_postrun(task_id="t3", state="SUCCESS", sender=_MockTask("app.tasks.email_task.send_email"))

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        by_task = {p.attributes["task"]: p.value for p in points}
        assert by_task["app.tasks.preview.render_preview"] == 2
        assert by_task["app.tasks.email_task.send_email"] == 1


class TestCeleryTasksFailed:
    def test_failure_increments_counter(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.maintenance.cleanup")

        class _Err(Exception):
            pass

        ca._on_task_failure(task_id="t1", exception=_Err("boom"), sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert len(points) == 1
        assert points[0].attributes == {"state": "failed", "task": "app.tasks.maintenance.cleanup"}

    def test_revoked_task_uses_revoked_state(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.deletion.delete_user")

        class Revoked(Exception):
            pass

        ca._on_task_failure(task_id="t1", exception=Revoked(), sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert points[0].attributes["state"] == "revoked"

    def test_none_sender_uses_unknown_task(self, patched_celery_metrics):
        ca._on_task_failure(task_id="t1", exception=Exception("x"), sender=None)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert points[0].attributes["task"] == "unknown"


class TestCeleryTasksRetried:
    def test_retry_increments_counter(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.email_task.send_email")
        ca._on_task_retry(sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert len(points) == 1
        assert points[0].attributes == {"state": "retried", "task": "app.tasks.email_task.send_email"}

    def test_multiple_retries_accumulate(self, patched_celery_metrics):
        sender = _MockTask("app.tasks.email_task.send_email")
        ca._on_task_retry(sender=sender)
        ca._on_task_retry(sender=sender)
        ca._on_task_retry(sender=sender)

        points = _get_data_points(patched_celery_metrics, "weftmark.celery.tasks")
        assert points[0].value == 3
