from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cron: Mapped[str] = mapped_column(String(100), nullable=False, default="0 2 * * *")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
