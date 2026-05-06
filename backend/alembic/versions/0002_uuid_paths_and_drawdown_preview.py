"""Add drawdown_preview columns; migrate all stored file paths to UUID flat naming.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-06

Changes:
- drafts: add drawdown_preview_path (VARCHAR 512), drawdown_preview_scale (INTEGER)
- All stored file paths (drafts, looms, yarn, projects) migrated from semantic
  keys (e.g. drafts/{id}/original.wif) to flat UUID keys (e.g. drafts/{uuid}.wif).
  Old files are left in storage; a follow-up cleanup task can remove them once the
  migration is confirmed stable.

Idempotent: skips rows whose path already matches the new scheme.
"""

# ruff: noqa: E501
import re
import uuid as _uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Matches the new scheme: {prefix}/{uuid}.{ext}  (exactly one slash, UUID stem)
_NEW_SCHEME = re.compile(
    r"^[^/]+/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[^./]+$"
)


def _is_new(path: str | None) -> bool:
    return not path or bool(_NEW_SCHEME.match(path))


def _migrate_path(path: str | None, prefix: str, file_uuid: _uuid.UUID | None = None) -> str | None:
    """Copy file to a new UUID key and return the new path, or return path unchanged on failure."""
    if _is_new(path):
        return path
    try:
        from app.services.storage import _get, _put
        data = _get(path)
        ext = Path(path).suffix
        new_uuid = file_uuid or _uuid.uuid4()
        new_path = f"{prefix}/{new_uuid}{ext}"
        _put(new_path, data)
        return new_path
    except Exception:
        return path  # file missing or write failed — leave as-is


def upgrade() -> None:
    # ── DDL: add new columns ────────────────────────────────────────────────
    op.add_column("drafts", sa.Column("drawdown_preview_path", sa.String(512), nullable=True))
    op.add_column("drafts", sa.Column("drawdown_preview_scale", sa.Integer(), nullable=True))

    # ── Data: migrate file paths to UUID flat scheme ─────────────────────────
    conn = op.get_bind()
    _migrate_all(conn)


def downgrade() -> None:
    op.drop_column("drafts", "drawdown_preview_scale")
    op.drop_column("drafts", "drawdown_preview_path")


def _migrate_all(conn) -> None:
    # Drafts — wif_path, wif_modified_path, preview_path each get new UUIDs
    rows = conn.execute(sa.text(
        "SELECT id, wif_path, wif_modified_path, preview_path FROM drafts"
    )).fetchall()
    for row in rows:
        new_wif = _migrate_path(row.wif_path, "drafts")
        new_mod = _migrate_path(row.wif_modified_path, "drafts")
        new_prev = _migrate_path(row.preview_path, "drafts")
        if new_wif != row.wif_path or new_mod != row.wif_modified_path or new_prev != row.preview_path:
            conn.execute(
                sa.text(
                    "UPDATE drafts SET wif_path=:w, wif_modified_path=:m, preview_path=:p WHERE id=:id"
                ),
                {"w": new_wif, "m": new_mod, "p": new_prev, "id": str(row.id)},
            )

    # Looms — profile photo (generate new UUID; loom.id is not the file ID)
    rows = conn.execute(sa.text("SELECT id, photo_path FROM looms WHERE photo_path IS NOT NULL")).fetchall()
    for row in rows:
        new_path = _migrate_path(row.photo_path, "looms")
        if new_path != row.photo_path:
            conn.execute(
                sa.text("UPDATE looms SET photo_path=:p WHERE id=:id"),
                {"p": new_path, "id": str(row.id)},
            )

    # LoomVersionPhoto — use the row's own id as the UUID key
    rows = conn.execute(sa.text("SELECT id, path FROM loom_version_photos")).fetchall()
    for row in rows:
        new_path = _migrate_path(row.path, "looms", file_uuid=_uuid.UUID(str(row.id)))
        if new_path != row.path:
            conn.execute(
                sa.text("UPDATE loom_version_photos SET path=:p WHERE id=:id"),
                {"p": new_path, "id": str(row.id)},
            )

    # LoomVersionReceipt — use the row's own id as the UUID key
    rows = conn.execute(sa.text("SELECT id, path FROM loom_version_receipts")).fetchall()
    for row in rows:
        new_path = _migrate_path(row.path, "looms", file_uuid=_uuid.UUID(str(row.id)))
        if new_path != row.path:
            conn.execute(
                sa.text("UPDATE loom_version_receipts SET path=:p WHERE id=:id"),
                {"p": new_path, "id": str(row.id)},
            )

    # Yarn — profile photo (generate new UUID)
    rows = conn.execute(sa.text("SELECT id, photo_path FROM yarn WHERE photo_path IS NOT NULL")).fetchall()
    for row in rows:
        new_path = _migrate_path(row.photo_path, "yarn")
        if new_path != row.photo_path:
            conn.execute(
                sa.text("UPDATE yarn SET photo_path=:p WHERE id=:id"),
                {"p": new_path, "id": str(row.id)},
            )

    # ProjectPhoto — use the row's own id as the UUID key
    rows = conn.execute(sa.text("SELECT id, file_path FROM project_photos")).fetchall()
    for row in rows:
        new_path = _migrate_path(row.file_path, "projects", file_uuid=_uuid.UUID(str(row.id)))
        if new_path != row.file_path:
            conn.execute(
                sa.text("UPDATE project_photos SET file_path=:p WHERE id=:id"),
                {"p": new_path, "id": str(row.id)},
            )
