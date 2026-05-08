"""Add config column to scheduled_tasks and seed new scheduled tasks.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-08

Changes:
- Adds config JSONB column to scheduled_tasks (nullable=false, default '{}')
- Seeds 6 new scheduled tasks (all disabled by default)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

_NEW_TASKS = [
    (
        "s3_audit",
        "S3 Orphan Audit",
        "Scans S3 bucket for files not referenced in the database. "
        "Results are flagged in the admin warning banner. "
        "Not applicable when STORAGE_BACKEND=local.",
        "0 3 * * 0",
        "{}",
    ),
    (
        "stale_signup_dismissal",
        "Stale Signup Dismissal",
        "Auto-dismisses pending signup requests older than the configured threshold. "
        "Dismissed signups are removed with no notification sent.",
        "0 4 * * *",
        '{"days": 30}',
    ),
    (
        "invite_pruning",
        "Expired Invite Pruning",
        "Deletes expired, accepted, and revoked invite records older than the retention window. "
        "Active (pending, not expired) invites are never deleted.",
        "30 3 * * 1",
        '{"retention_days": 90}',
    ),
    (
        "audit_log_pruning",
        "Audit Log Pruning",
        "Deletes audit log entries older than the retention window. "
        "Security events (user.banned, user.deleted, user.elevated) are never pruned.",
        "0 3 * * 2",
        '{"retention_days": 90}',
    ),
    (
        "heartbeat",
        "Worker Heartbeat",
        "No-op task that records itself in the task history every 15 minutes. "
        "Absence of recent heartbeat entries indicates a worker outage.",
        "*/15 * * * *",
        "{}",
    ),
    (
        "preview_retry",
        "Failed Preview Retry",
        "Re-dispatches drawdown preview generation for drafts missing a preview. "
        "Skips drafts uploaded in the last 10 minutes to avoid racing initial generation.",
        "0 5 * * *",
        '{"limit": 50}',
    ),
]


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
    )
    for name, display_name, description, cron, config in _NEW_TASKS:
        op.execute(
            f"""
            INSERT INTO scheduled_tasks (name, display_name, description, enabled, cron, config)
            VALUES (
                '{name}',
                '{display_name}',
                '{description}',
                false,
                '{cron}',
                '{config}'::jsonb
            )
            ON CONFLICT (name) DO NOTHING
            """
        )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "config")
