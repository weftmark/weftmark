import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

SKEIN_STATUSES = ("available", "in_use", "consumed")

WEIGHT_CATEGORIES = (
    "thread",
    "lace",
    "fingering",
    "sport",
    "dk",
    "worsted",
    "aran",
    "bulky",
    "super_bulky",
)


class Yarn(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "yarns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    brand: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    weight_notation: Mapped[str | None] = mapped_column(String(20), nullable=True)  # e.g. "8/2"
    weight_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fiber_content: Mapped[str | None] = mapped_column(String(255), nullable=True)

    color_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "#rrggbb"

    unit_weight_oz: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    unit_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    unit_yardage: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)
    yards_per_pound: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)

    sett_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sett_max: Mapped[int | None] = mapped_column(Integer, nullable=True)

    purchase_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ravelry_stash_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    ravelry_yarn_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    ravelry_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ravelry_thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ravelry_colorway_photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ravelry_colorway_thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ravelry_permalink: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ravelry_discontinued: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ravelry_machine_washable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ravelry_yarn_company_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when Ravelry removes the entry from the user's stash but we retain it for history/project references
    out_of_stash: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # User-managed or auto-set (when out_of_stash becomes True); hidden from the default list view
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    skeins: Mapped[list["Skein"]] = relationship("Skein", back_populates="yarn", order_by="Skein.created_at")
    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])  # type: ignore[name-defined]


class Skein(Base, TimestampMixin):
    __tablename__ = "skeins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    yarn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("yarns.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")

    current_yardage: Mapped[Decimal | None] = mapped_column(Numeric(10, 1), nullable=True)
    current_weight_oz: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    current_weight_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    yarn: Mapped["Yarn"] = relationship("Yarn", back_populates="skeins")
