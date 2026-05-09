from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.metrics import Observation

_meter = metrics.get_meter("weftmark.business")

signups_total = _meter.create_counter(
    "weftmark.user.signups",
    description="User signups received via Clerk user.created webhook",
    unit="1",
)

signups_approved_total = _meter.create_counter(
    "weftmark.user.signups_approved",
    description="Pending signups approved by an admin",
    unit="1",
)

eula_accepted_total = _meter.create_counter(
    "weftmark.user.eula_accepted",
    description="EULA acceptances",
    unit="1",
)

role_changes_total = _meter.create_counter(
    "weftmark.user.role_changes",
    description="User role changes applied by an admin",
    unit="1",
)

logins_total = _meter.create_counter(
    "weftmark.user.logins",
    description="User logins via Clerk session.created webhook",
    unit="1",
)

celery_tasks_total = _meter.create_counter(
    "weftmark.celery.tasks",
    description="Celery task executions by outcome (succeeded/failed/retried/revoked)",
    unit="1",
)


def register_pool_metrics(engine) -> None:
    """Register SQLAlchemy pool observable gauges. Call once after MeterProvider is set."""
    pool = engine.sync_engine.pool

    _meter.create_observable_gauge(
        "weftmark.db.pool.size",
        callbacks=[lambda _: [Observation(pool.size())]],
        description="SQLAlchemy connection pool configured size",
        unit="connections",
    )
    _meter.create_observable_gauge(
        "weftmark.db.pool.checked_out",
        callbacks=[lambda _: [Observation(pool.checkedout())]],
        description="Connections currently checked out (in use by queries)",
        unit="connections",
    )
    _meter.create_observable_gauge(
        "weftmark.db.pool.checked_in",
        callbacks=[lambda _: [Observation(pool.checkedin())]],
        description="Connections currently idle in the pool",
        unit="connections",
    )
    _meter.create_observable_gauge(
        "weftmark.db.pool.overflow",
        callbacks=[lambda _: [Observation(pool.overflow())]],
        description="Overflow connections above pool_size (negative means unused capacity)",
        unit="connections",
    )
