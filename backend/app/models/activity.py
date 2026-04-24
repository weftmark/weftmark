import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

ACTIVITY_TYPES = ("treadle", "lift")
ACTIVITY_STATUSES = ("active", "completed", "abandoned")


class Activity(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    loom_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("looms.id"), nullable=True)
    loom_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loom_versions.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "treadle" | "lift"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Step tracking
    current_pick: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_picks: Mapped[int] = mapped_column(Integer, nullable=False)

    # Warp plan inputs
    finished_length_per_item: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    num_items: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    waste_between_items: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    warp_waste_allowance: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)
    length_unit: Mapped[str] = mapped_column(String(5), nullable=False, default="cm")

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list["ActivityStep"]] = relationship(
        "ActivityStep", back_populates="activity", order_by="ActivityStep.created_at"
    )


class ActivityStep(Base, TimestampMixin):
    __tablename__ = "activity_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "advance" | "reverse"
    from_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    to_pick: Mapped[int] = mapped_column(Integer, nullable=False)

    activity: Mapped["Activity"] = relationship("Activity", back_populates="steps")
