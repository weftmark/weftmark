import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

PROJECT_TYPES = ("treadle", "lift")
PROJECT_STATUSES = ("active", "completed", "abandoned")


class ProjectPhoto(Base, TimestampMixin):
    __tablename__ = "project_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project: Mapped["Project"] = relationship("Project", back_populates="photos")


class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("drafts.id"), nullable=False, index=True)
    loom_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("looms.id"), nullable=True)
    loom_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loom_versions.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "treadle" | "lift"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Step tracking
    current_pick: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_item: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_picks: Mapped[int] = mapped_column(Integer, nullable=False)
    # Stores last known pick per item: {"1": 3, "2": 7}. Updated on item transitions so
    # jumping back to a previously visited item restores where the weaver left off.
    item_picks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Warp plan inputs
    finished_length_per_item: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    num_items: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    waste_between_items: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    warp_waste_allowance: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    length_unit: Mapped[str] = mapped_column(String(5), nullable=False, default="cm")

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hide_unused_shafts_treadles: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    steps: Mapped[list["ProjectStep"]] = relationship(
        "ProjectStep", back_populates="project", order_by="ProjectStep.created_at"
    )
    sessions: Mapped[list["WeaveSession"]] = relationship(
        "WeaveSession", back_populates="project", order_by="WeaveSession.started_at"
    )
    photos: Mapped[list["ProjectPhoto"]] = relationship(
        "ProjectPhoto", back_populates="project", order_by="ProjectPhoto.display_order"
    )


class ProjectStep(Base, TimestampMixin):
    __tablename__ = "project_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "advance" | "reverse"
    from_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    to_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="steps")


class WeaveSession(Base, TimestampMixin):
    __tablename__ = "weave_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="sessions")
