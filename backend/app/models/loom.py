import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

LOOM_TYPES = ("floor_loom", "table_loom", "rigid_heddle", "inkle", "dobby", "other")

# Only these types support project tracking (treadle or lift).
PROJECT_SUPPORTED_LOOM_TYPES = frozenset({"floor_loom", "table_loom"})


def loom_tracking_flags(loom_type: str) -> tuple[bool, bool]:
    """Return (supports_lift_tracking, supports_treadle_tracking) derived from loom_type."""
    return loom_type == "table_loom", loom_type == "floor_loom"


class Loom(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "looms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    loom_type: Mapped[str] = mapped_column(String(30), nullable=False, default="floor_loom")

    # Identity
    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Purchase info
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Profile photo (single, replaced on upload)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Supported project types
    supports_lift_tracking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_treadle_tracking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list["LoomVersion"]] = relationship(
        "LoomVersion", back_populates="loom", order_by="LoomVersion.version_number"
    )
    reeds: Mapped[list["LoomReed"]] = relationship(
        "LoomReed", back_populates="loom", order_by="LoomReed.dents_per_inch", cascade="all, delete-orphan"
    )
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])  # type: ignore[name-defined]

    @property
    def current_version(self) -> "LoomVersion | None":
        return self.versions[-1] if self.versions else None


class LoomVersion(Base, TimestampMixin):
    __tablename__ = "loom_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("looms.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    photos: Mapped[list["LoomVersionPhoto"]] = relationship(
        "LoomVersionPhoto",
        back_populates="version",
        order_by="LoomVersionPhoto.display_order",
        cascade="all, delete-orphan",
    )
    receipts: Mapped[list["LoomVersionReceipt"]] = relationship(
        "LoomVersionReceipt",
        back_populates="version",
        order_by="LoomVersionReceipt.created_at",
        cascade="all, delete-orphan",
    )
    accessories: Mapped[list["LoomVersionAccessory"]] = relationship(
        "LoomVersionAccessory",
        back_populates="version",
        order_by="LoomVersionAccessory.created_at",
        cascade="all, delete-orphan",
    )


class LoomVersionPhoto(Base, TimestampMixin):
    __tablename__ = "loom_version_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loom_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loom_versions.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped["LoomVersion"] = relationship("LoomVersion", back_populates="photos")


class LoomVersionReceipt(Base, TimestampMixin):
    __tablename__ = "loom_version_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loom_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loom_versions.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped["LoomVersion"] = relationship("LoomVersion", back_populates="receipts")


class LoomVersionAccessory(Base, TimestampMixin):
    __tablename__ = "loom_version_accessories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loom_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loom_versions.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped["LoomVersion"] = relationship("LoomVersion", back_populates="accessories")


class LoomReed(Base, TimestampMixin):
    __tablename__ = "loom_reeds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loom_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("looms.id"), nullable=False, index=True)
    dents_per_inch: Mapped[float] = mapped_column(Float, nullable=False)
    width_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    loom: Mapped["Loom"] = relationship("Loom", back_populates="reeds")
