import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import Boolean, Date, Integer, Numeric, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, SoftDeleteMixin

LOOM_TYPES = ("floor_loom", "table_loom", "rigid_heddle", "inkle", "other")


class Loom(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "looms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    loom_type: Mapped[str] = mapped_column(String(30), nullable=False, default="floor_loom")

    # Identity
    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Purchase info
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Supported activity types
    supports_lift_tracking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_treadle_tracking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list["LoomVersion"]] = relationship(
        "LoomVersion", back_populates="loom", order_by="LoomVersion.version_number"
    )
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])  # type: ignore[name-defined]

    @property
    def current_version(self) -> "LoomVersion | None":
        return self.versions[-1] if self.versions else None


class LoomVersion(Base, TimestampMixin):
    __tablename__ = "loom_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    loom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("looms.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Spec snapshot — nullable because not all loom types use every field
    num_shafts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_treadles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_heddles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weaving_width: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    weaving_width_unit: Mapped[str] = mapped_column(String(5), default="cm", nullable=False)
    warp_waste_allowance: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    warp_waste_unit: Mapped[str] = mapped_column(String(5), default="cm", nullable=False)

    loom: Mapped["Loom"] = relationship("Loom", back_populates="versions")
