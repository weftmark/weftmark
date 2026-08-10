"""add draft fingerprints

Revision ID: f5b642eba518
Revises: 6e23527ac637
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5b642eba518'
down_revision: Union[str, None] = '6e23527ac637'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("threading_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("drafts", sa.Column("tieup_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("drafts", sa.Column("drawdown_fingerprint", sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_drafts_threading_fingerprint'), 'drafts', ['threading_fingerprint'], unique=False)
    op.create_index(op.f('ix_drafts_tieup_fingerprint'), 'drafts', ['tieup_fingerprint'], unique=False)
    op.create_index(op.f('ix_drafts_drawdown_fingerprint'), 'drafts', ['drawdown_fingerprint'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_drafts_drawdown_fingerprint'), table_name='drafts')
    op.drop_index(op.f('ix_drafts_tieup_fingerprint'), table_name='drafts')
    op.drop_index(op.f('ix_drafts_threading_fingerprint'), table_name='drafts')
    op.drop_column("drafts", "drawdown_fingerprint")
    op.drop_column("drafts", "tieup_fingerprint")
    op.drop_column("drafts", "threading_fingerprint")
