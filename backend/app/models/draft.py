import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, RetireMixin, SoftDeleteMixin, TimestampMixin


class Draft(Base, TimestampMixin, SoftDeleteMixin, RetireMixin):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Original WIF file (never mutated after upload)
    wif_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    wif_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # App-modified WIF (accumulates changes like generated liftplan, metadata overrides;
    # original wif_path is never mutated after upload)
    wif_modified_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Tracks metadata values overridden by the user e.g. {"num_treadles": {"original": 11, "override": 10}}
    metadata_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Parsed WIF metadata
    num_shafts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_treadles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warp_threads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weft_threads: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Effective counts derived from actual treadling/liftplan data (may differ from declared metadata)
    effective_num_treadles: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_num_shafts: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Feature availability flags
    has_threading: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_tieup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_treadling: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_liftplan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_color_palette: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    liftplan_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Lint results (arrays of message strings)
    lint_warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    lint_errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # User-reported source software (for WIF compatibility tracking)
    wif_source_software: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wif_source_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Rendered preview image path
    preview_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Pre-generated reduced-size drawdown for fast serving
    drawdown_preview_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    drawdown_preview_scale: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # WIF-extracted dimensional measurements (normalized to cm where applicable).
    # Keys: warp_length, warp_length_original, warp_length_unit, warp_spacing, ...,
    #       weft_length, weft_length_original, weft_length_unit, weft_spacing, ...
    # Only keys that were present in the WIF are stored; {} or null if none found.
    wif_measurements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Color palette extracted from WIF [COLOR TABLE], normalized to 0–255 RGB.
    # List of {index, r, g, b, hex} objects sorted by index; null if no COLOR TABLE in WIF.
    wif_colors: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Pick count per weft color computed from LIFTPLAN or TREADLING.
    # List of {hex, count, percentage} sorted by count desc; null if no pick data.
    weft_color_stats: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Thread count per warp color from [WARP COLORS] / [WARP] Color= default.
    # List of {hex, count, percentage} sorted by count desc; null if no color data.
    warp_color_stats: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Effective warp length in cm — populated from WIF on import or set manually.
    warp_length_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # True when the user has explicitly overridden the WIF's warp_length value.
    warp_length_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # User-entered weaving width override in cm (null = derive from WIF weft_length or thread count × spacing).
    weaving_width_override_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # User-entered EPI override (ends per inch; null = derive from WIF warp_spacing or width ÷ thread count).
    epi_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sharing
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    share_slug: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    owner: Mapped["User"] = relationship("User", foreign_keys=[owner_id])  # type: ignore[name-defined]
