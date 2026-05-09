from opentelemetry import metrics

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
