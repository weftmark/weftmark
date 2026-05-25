"""ravelry integration: oauth states, credentials, yarn stash id

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0037_ravelry_integration"
down_revision = "0036_export_archive_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ravelry_oauth_states",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ravelry_oauth_states_user_id", "ravelry_oauth_states", ["user_id"])

    op.create_table(
        "ravelry_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("ravelry_username", sa.String(100), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stash_etag", sa.String(255), nullable=True),
        sa.Column("stash_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ravelry_credentials_user_id", "ravelry_credentials", ["user_id"], unique=True)

    op.add_column("yarns", sa.Column("ravelry_stash_id", sa.BigInteger, nullable=True))
    op.create_index("ix_yarns_ravelry_stash_id", "yarns", ["ravelry_stash_id"])
    op.add_column("yarns", sa.Column("out_of_stash", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("yarns", sa.Column("archived", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("yarns", "archived")
    op.drop_column("yarns", "out_of_stash")
    op.drop_index("ix_yarns_ravelry_stash_id", table_name="yarns")
    op.drop_column("yarns", "ravelry_stash_id")
    op.drop_index("ix_ravelry_credentials_user_id", table_name="ravelry_credentials")
    op.drop_table("ravelry_credentials")
    op.drop_index("ix_ravelry_oauth_states_user_id", table_name="ravelry_oauth_states")
    op.drop_table("ravelry_oauth_states")
