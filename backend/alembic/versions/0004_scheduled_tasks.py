"""Create scheduled_tasks table and seed built-in tasks.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-07

Changes:
- Creates scheduled_tasks table (name PK, enabled, cron, display_name, description, last_fired_at, updated_at)
- Seeds the cve_scan task (disabled by default, daily at 02:00 UTC)
"""

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cron", sa.String(100), nullable=False, server_default="0 2 * * *"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        INSERT INTO scheduled_tasks (name, display_name, description, enabled, cron)
        VALUES (
            'cve_scan',
            'CVE Scan',
            'Scans Python dependencies via pip-audit for known vulnerabilities. '
            'Results are stored and shown in the CVE Scan tab and admin warning banner.',
            false,
            '0 2 * * *'
        )
        ON CONFLICT (name) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("scheduled_tasks")
