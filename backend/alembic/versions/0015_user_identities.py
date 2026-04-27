"""add user_identities table for multi-provider OIDC

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_sub", sa.String(256), nullable=False),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("provider", "provider_sub", name="uq_user_identities_provider_sub"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    # Seed existing users as 'google' identities (matches the legacy single-provider setup).
    # Users who re-login before this row exists are caught by the oidc_sub fallback in auth.py.
    op.execute(
        sa.text(
            """
            INSERT INTO user_identities (id, user_id, provider, provider_sub, email, created_at)
            SELECT gen_random_uuid(), id, 'google', oidc_sub, email, NOW()
            FROM users
            WHERE oidc_sub IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
