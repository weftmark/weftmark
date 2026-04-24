"""
WIF file linter.

Parses the WIF file with configparser (not PyWeaving) so we get lint results
even for files that PyWeaving would reject. Reports which features are available
and flags missing or problematic sections.
"""

from __future__ import annotations

from configparser import RawConfigParser
from dataclasses import dataclass, field


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Parsed metadata
    num_shafts: int | None = None
    num_treadles: int | None = None
    warp_threads: int | None = None
    weft_threads: int | None = None

    # Feature flags
    has_threading: bool = False
    has_tieup: bool = False
    has_treadling: bool = False
    has_liftplan: bool = False
    has_color_palette: bool = False

    # Source software extracted from [WIF] section
    source_software: str | None = None
    source_version: str | None = None

    @property
    def is_parseable(self) -> bool:
        return not any("Cannot parse" in e for e in self.errors)


def lint(wif_bytes: bytes) -> LintResult:
    result = LintResult()

    # Decode — WIF files are typically ASCII or Latin-1
    try:
        text = wif_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = wif_bytes.decode("latin-1")

    config = RawConfigParser()
    config.optionxform = str  # preserve key case
    try:
        config.read_string(text)
    except Exception as exc:
        result.errors.append(f"Cannot parse file: {exc}")
        return result

    sections = {s.upper() for s in config.sections()}

    # --- Required sections ---
    if "WIF" not in sections:
        result.errors.append("Missing [WIF] section — file may not be a valid WIF file")

    if "WEAVING" not in sections:
        result.errors.append("Missing [WEAVING] section — shaft and treadle count unavailable")
    else:
        try:
            result.num_shafts = config.getint("WEAVING", "Shafts")
        except Exception:
            result.warnings.append("Could not read shaft count from [WEAVING]")
        try:
            result.num_treadles = config.getint("WEAVING", "Treadles")
        except Exception:
            result.warnings.append("Could not read treadle count from [WEAVING]")

    # --- Source software (for compatibility tracking) ---
    if "WIF" in sections:
        result.source_software = _get(config, "WIF", "Source Program")
        result.source_version = _get(config, "WIF", "Source Version")

    # --- Feature detection ---
    result.has_threading = "THREADING" in sections
    result.has_tieup = "TIEUP" in sections
    result.has_treadling = "TREADLING" in sections
    result.has_liftplan = "LIFTPLAN" in sections
    result.has_color_palette = "COLOR PALETTE" in sections or "COLOR TABLE" in sections

    # Warp/weft thread counts
    if "WARP" in sections:
        try:
            result.warp_threads = config.getint("WARP", "Threads")
        except Exception:
            pass
    if "WEFT" in sections:
        try:
            result.weft_threads = config.getint("WEFT", "Threads")
        except Exception:
            pass

    # --- Warnings for missing optional sections ---
    if not result.has_threading:
        result.warnings.append("No [THREADING] section — threading diagram unavailable")
    if not result.has_tieup and not result.has_liftplan:
        result.warnings.append("No [TIEUP] or [LIFTPLAN] section — tie-up grid and activity tracking unavailable")
    if not result.has_treadling and not result.has_liftplan:
        result.warnings.append(
            "No [TREADLING] or [LIFTPLAN] section — step tracking unavailable for all activity types"
        )
    if not result.has_color_palette:
        result.warnings.append("No [COLOR PALETTE] or [COLOR TABLE] section — preview will render in default colors")
    if result.has_treadling and result.has_liftplan:
        result.warnings.append(
            "File contains both [TREADLING] and [LIFTPLAN] — only one will be used per activity type"
        )

    return result


def _get(config: RawConfigParser, section: str, key: str) -> str | None:
    try:
        return config.get(section, key).strip() or None
    except Exception:
        return None
