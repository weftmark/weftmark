"""
Parse treadling and liftplan pick data from WIF bytes.

Returns a list of picks, each with the set of active treadles or shafts (1-indexed),
plus optional per-pick weft color derived from [COLOR TABLE] and [WEFT COLORS].
"""

from __future__ import annotations

from configparser import RawConfigParser
from dataclasses import dataclass


@dataclass
class PickData:
    activity_type: str  # "treadle" | "lift"
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


def parse_picks(wif_bytes: bytes, activity_type: str) -> PickData:
    try:
        text = wif_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = wif_bytes.decode("latin-1")

    config = RawConfigParser()
    config.optionxform = str
    config.read_string(text)

    section = "TREADLING" if activity_type == "treadle" else "LIFTPLAN"

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

    weft_color_map: dict[int, int] = {}
    if config.has_section("WEFT COLORS"):
        for k, v in config.items("WEFT COLORS"):
            try:
                # Spec: read only the first integer (palette index)
                weft_color_map[int(k)] = int(v.split(",")[0].strip())
            except ValueError:
                continue

    weft_colors: list[str | None] = [
        colors.get(weft_color_map[i]) if i in weft_color_map else None for i in range(1, max_pick + 1)
    ]

    return PickData(activity_type=activity_type, total_picks=max_pick, picks=picks, weft_colors=weft_colors)


def compute_liftplan(wif_bytes: bytes) -> bytes:
    """
    Compute a [LIFTPLAN] section from [TREADLING] + [TIEUP] and append it.
    Returns updated WIF bytes. Raises ValueError if required sections are missing.

    Algorithm: for each pick, union the shafts from every treadle pressed.
    """
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
