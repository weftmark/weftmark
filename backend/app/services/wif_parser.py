"""
Parse treadling, liftplan, and dimensional measurements from WIF bytes.
"""

from __future__ import annotations

from configparser import RawConfigParser
from dataclasses import dataclass

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# WIF unit → (canonical label, cm multiplier)
_UNIT_CONVERSIONS: dict[str, tuple[str, float]] = {
    "centimeters": ("cm", 1.0),
    "inches": ("in", 2.54),
    "decipoints": ("dp", 2.54 / 720),
}


def _parse_unit(raw: str) -> tuple[str, float]:
    """Return (canonical_label, cm_multiplier). Defaults to inches per WIF spec."""
    return _UNIT_CONVERSIONS.get(raw.lower().strip(), ("in", 2.54))


def extract_measurements(wif_bytes: bytes) -> dict:
    """Extract dimensional measurements from WIF [WARP] and [WEFT] sections.

    Returns a dict with a subset of these keys (only present if found in WIF):
      warp_length, warp_length_original, warp_length_unit
      warp_spacing, warp_spacing_original, warp_spacing_unit
      weft_length, weft_length_original, weft_length_unit
      weft_spacing, weft_spacing_original, weft_spacing_unit

    *_length and *_spacing values are normalized to centimeters.
    *_original values are the raw numbers from the WIF file.
    *_unit values are the canonical label ("in", "cm", "dp").
    Never raises — returns {} on any parse failure.
    """
    try:
        try:
            text = wif_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = wif_bytes.decode("latin-1")

        config = RawConfigParser()
        config.optionxform = str
        config.read_string(text)

        result: dict = {}

        for section, prefix in (("WARP", "warp"), ("WEFT", "weft")):
            if not config.has_section(section):
                continue

            raw_unit = ""
            try:
                raw_unit = config.get(section, "Units").strip()
            except Exception:
                pass
            unit_label, multiplier = _parse_unit(raw_unit or "Inches")

            try:
                length_val = float(config.get(section, "Length").strip())
                result[f"{prefix}_length_original"] = length_val
                result[f"{prefix}_length_unit"] = unit_label
                result[f"{prefix}_length"] = round(length_val * multiplier, 4)
            except Exception:
                pass

            try:
                spacing_val = float(config.get(section, "Spacing").strip())
                result[f"{prefix}_spacing_original"] = spacing_val
                result[f"{prefix}_spacing_unit"] = unit_label
                result[f"{prefix}_spacing"] = round(spacing_val * multiplier, 4)
            except Exception:
                pass

        return result
    except Exception:
        return {}


def extract_colors(wif_bytes: bytes) -> list[dict]:
    """Extract only the colors referenced in the design from WIF [COLOR TABLE].

    A color is considered "used" if its palette index appears in any of:
      [WEFT COLORS], [WARP COLORS], [WEFT] Color=, [WARP] Color=

    Returns a list of dicts, each with:
      index (int), r (int, 0–255), g (int, 0–255), b (int, 0–255), hex (str)

    Values are normalized from the [COLOR PALETTE] Range to 0–255.
    Returns [] if no color table exists or no colors are referenced in the design.
    Never raises.
    """
    try:
        try:
            text = wif_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = wif_bytes.decode("latin-1")

        config = RawConfigParser()
        config.optionxform = str
        config.read_string(text)

        if not config.has_section("COLOR TABLE"):
            return []

        # Collect palette indices actually referenced in the design.
        used: set[int] = set()

        for sect in ("WEFT", "WARP"):
            if config.has_section(sect):
                try:
                    used.add(int(config.get(sect, "Color").split(",")[0].strip()))
                except Exception:
                    pass

        for sect in ("WEFT COLORS", "WARP COLORS"):
            if config.has_section(sect):
                for _, v in config.items(sect):
                    try:
                        used.add(int(v.split(",")[0].strip()))
                    except ValueError:
                        continue

        if not used:
            return []

        scale = _color_scale(config)
        colors: list[dict] = []

        for k, v in config.items("COLOR TABLE"):
            try:
                idx = int(k)
                if idx not in used:
                    continue
                parts = [int(p.strip()) for p in v.split(",")]
                if len(parts) < 3:
                    continue
                r, g, b = parts[:3]
                if scale != 255:
                    r = round(r * 255 / scale)
                    g = round(g * 255 / scale)
                    b = round(b * 255 / scale)
                r, g, b = (max(0, min(255, c)) for c in (r, g, b))
                colors.append({"index": idx, "r": r, "g": g, "b": b, "hex": f"#{r:02x}{g:02x}{b:02x}"})
            except (ValueError, ZeroDivisionError):
                continue

        colors.sort(key=lambda c: c["index"])
        return colors
    except Exception:
        return []


def extract_weft_color_stats(wif_bytes: bytes) -> list[dict]:
    """Count picks per weft color from LIFTPLAN (preferred) or TREADLING + TIEUP.

    Returns a list of dicts sorted by count descending:
      hex (str), count (int), percentage (float, 0–100, rounded to 1 dp)

    Returns [] if no treadling/liftplan section exists or no colors are defined.
    Never raises.
    """
    try:
        try:
            text = wif_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = wif_bytes.decode("latin-1")

        config = RawConfigParser()
        config.optionxform = str
        config.read_string(text)

        project_type: str | None = None
        if config.has_section("LIFTPLAN"):
            project_type = "lift"
        elif config.has_section("TREADLING"):
            project_type = "treadle"

        if project_type is None:
            return []

        pick_data = parse_picks(wif_bytes, project_type)
        total = len(pick_data.weft_colors)
        if total == 0:
            return []

        counts: dict[str, int] = {}
        for hex_color in pick_data.weft_colors:
            if hex_color is None:
                continue
            counts[hex_color] = counts.get(hex_color, 0) + 1

        if not counts:
            return []

        counted = sum(counts.values())
        result = [
            {
                "hex": hex_color,
                "count": count,
                "percentage": round(count * 100 / counted, 1),
            }
            for hex_color, count in sorted(counts.items(), key=lambda x: -x[1])
        ]
        return result
    except Exception:
        return []


@dataclass
class PickData:
    project_type: str  # "treadle" | "lift"
    total_picks: int
    picks: list[list[int]]  # index 0 = pick 1; each inner list = active treadles/shafts
    weft_colors: list[str | None]  # hex color per pick (e.g. "#ff0000"), None if undefined


def _color_scale(config: RawConfigParser) -> int:
    """Return the max value from [COLOR PALETTE] Range (default 255)."""
    try:
        parts = config.get("COLOR PALETTE", "Range").split(",")
        return int(parts[1].strip())
    except Exception:
        return 255


def _color_table(config: RawConfigParser, scale: int) -> dict[int, str]:
    """Parse [COLOR TABLE] into {index: '#rrggbb'}, scaling from `scale` to 0-255."""
    table: dict[int, str] = {}
    if not config.has_section("COLOR TABLE"):
        return table
    for k, v in config.items("COLOR TABLE"):
        try:
            idx = int(k)
            # Some WIF files use "PaletteIdx,R,G,B" — spec says ignore R,G,B, use table
            parts = [int(p.strip()) for p in v.split(",")]
            if len(parts) < 3:
                continue
            r, g, b = parts[:3]
            if scale != 255:
                r = round(r * 255 / scale)
                g = round(g * 255 / scale)
                b = round(b * 255 / scale)
            r, g, b = (max(0, min(255, c)) for c in (r, g, b))
            table[idx] = f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, ZeroDivisionError):
            continue
    return table


def parse_picks(wif_bytes: bytes, project_type: str) -> PickData:
    with tracer.start_as_current_span("wif.parse_picks") as span:
        span.set_attribute("wif.project_type", project_type)

        try:
            text = wif_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = wif_bytes.decode("latin-1")

        config = RawConfigParser()
        config.optionxform = str
        config.read_string(text)

        section = "TREADLING" if project_type == "treadle" else "LIFTPLAN"

        if not config.has_section(section):
            raise ValueError(f"WIF file has no [{section}] section")

        raw = dict(config.items(section))

        max_pick = max(int(k) for k in raw)
        picks: list[list[int]] = []
        for i in range(1, max_pick + 1):
            val = raw.get(str(i), "")
            active = [int(x.strip()) for x in val.split(",") if x.strip()] if val.strip() else []
            picks.append(active)

        # Parse weft colors
        scale = _color_scale(config)
        colors = _color_table(config, scale)

        # Global default weft color from [WEFT] Color= key (palette index)
        default_weft_color: str | None = None
        if config.has_section("WEFT"):
            try:
                default_idx = int(config.get("WEFT", "Color").split(",")[0].strip())
                default_weft_color = colors.get(default_idx)
            except Exception:
                pass

        weft_color_map: dict[int, int] = {}
        if config.has_section("WEFT COLORS"):
            for k, v in config.items("WEFT COLORS"):
                try:
                    # Spec: read only the first integer (palette index)
                    weft_color_map[int(k)] = int(v.split(",")[0].strip())
                except ValueError:
                    continue

        weft_colors: list[str | None] = [
            colors.get(weft_color_map[i]) if i in weft_color_map else default_weft_color for i in range(1, max_pick + 1)
        ]

        result = PickData(project_type=project_type, total_picks=max_pick, picks=picks, weft_colors=weft_colors)
        span.set_attribute("wif.total_picks", result.total_picks)
        return result


def compute_liftplan(wif_bytes: bytes) -> bytes:
    """
    Compute a [LIFTPLAN] section from [TREADLING] + [TIEUP] and append it.
    Returns updated WIF bytes. Raises ValueError if required sections are missing.

    Algorithm: for each pick, union the shafts from every treadle pressed.
    """
    with tracer.start_as_current_span("wif.compute_liftplan") as span:
        try:
            text = wif_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = wif_bytes.decode("latin-1")

        config = RawConfigParser()
        config.optionxform = str
        config.read_string(text)

        if not config.has_section("TREADLING"):
            raise ValueError("WIF file has no [TREADLING] section — cannot compute lift plan")
        if not config.has_section("TIEUP"):
            raise ValueError("WIF file has no [TIEUP] section — cannot compute lift plan")

        # tieup[treadle_num] -> sorted list of shaft nums
        tieup: dict[int, list[int]] = {}
        for k, v in config.items("TIEUP"):
            treadle = int(k)
            shafts = sorted(int(s.strip()) for s in v.split(",") if s.strip())
            tieup[treadle] = shafts

        treadling_raw = dict(config.items("TREADLING"))
        max_pick = max(int(k) for k in treadling_raw)
        span.set_attribute("wif.total_picks", max_pick)

        lines = ["[LIFTPLAN]"]
        for i in range(1, max_pick + 1):
            val = treadling_raw.get(str(i), "")
            treadles = [int(t.strip()) for t in val.split(",") if t.strip()] if val.strip() else []
            shafts: set[int] = set()
            for t in treadles:
                shafts.update(tieup.get(t, []))
            lines.append(f"{i}={','.join(str(s) for s in sorted(shafts))}")

        updated = text.rstrip() + "\n\n" + "\n".join(lines) + "\n"
        return updated.encode("utf-8")
