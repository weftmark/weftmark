import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

DELETION_STATES = ("pending", "in_progress", "complete", "stalled", "aborted")


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    oidc_sub: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True, index=True)
    clerk_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(20), default="light", nullable=False)
    activity_theme: Mapped[str | None] = mapped_column(String(50), nullable=True)
    idle_timeout_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    measurement_system: Mapped[str] = mapped_column(String(10), default="metric", nullable=False)
    ai_training_consent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    eula_accepted_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    eula_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clerk_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deletion_state: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)
    deletion_initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    clerk_errored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
