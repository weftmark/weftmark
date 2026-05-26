"""
Tests for app.services.wif_parser.

Covers: pick parsing (treadle + lift), weft color extraction,
color scale normalisation, liftplan computation, encoding fallback.
"""

import pytest

from app.services.wif_parser import (
    PickData,
    ThreadingData,
    TieUpData,
    compute_liftplan,
    extract_colors,
    extract_measurements,
    extract_warp_color_stats,
    extract_weft_color_stats,
    parse_picks,
    parse_threading,
    parse_tieup,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def wif(extra: str = "", *, encoding: str = "utf-8") -> bytes:
    """Minimal valid WIF with a 4-shaft / 4-treadle structure."""
    text = f"""
[WIF]
Version=1.1
Source Program=TestSuite

[WEAVING]
Shafts=4
Treadles=4

[TREADLING]
1=1
2=2
3=3
4=4

[TIEUP]
1=1
2=2
3=3
4=4

{extra}
""".strip()
    return text.encode(encoding)


# ---------------------------------------------------------------------------
# parse_picks — treadle mode
# ---------------------------------------------------------------------------


class TestParsePicksTreadle:
    def test_returns_pick_data(self):
        data = parse_picks(wif(), "treadle")
        assert isinstance(data, PickData)
        assert data.project_type == "treadle"

    def test_total_picks(self):
        data = parse_picks(wif(), "treadle")
        assert data.total_picks == 4

    def test_pick_values(self):
        data = parse_picks(wif(), "treadle")
        assert data.picks[0] == [1]
        assert data.picks[1] == [2]
        assert data.picks[2] == [3]
        assert data.picks[3] == [4]

    def test_multi_treadle_pick(self):
        content = b"[WIF]\nVersion=1.1\n\n[TREADLING]\n1=1,3\n2=2,4"
        data = parse_picks(content, "treadle")
        assert data.picks[0] == [1, 3]
        assert data.picks[1] == [2, 4]

    def test_empty_pick(self):
        """A pick with no value maps to an empty active list."""
        content = b"[WIF]\nVersion=1.1\n\n[TREADLING]\n1=1\n2=\n3=3"
        data = parse_picks(content, "treadle")
        assert data.picks[0] == [1]
        assert data.picks[1] == []
        assert data.picks[2] == [3]

    def test_sparse_pick_numbers_filled_with_empty(self):
        """Picks 1-max are generated; missing intermediate picks are empty."""
        content = b"[WIF]\nVersion=1.1\n\n[TREADLING]\n1=1\n3=3"
        data = parse_picks(content, "treadle")
        assert data.total_picks == 3
        assert data.picks[0] == [1]
        assert data.picks[1] == []  # pick 2 absent → empty
        assert data.picks[2] == [3]

    def test_missing_section_raises(self):
        content = wif()  # has no extra LIFTPLAN; request lift anyway
        with pytest.raises(ValueError, match="LIFTPLAN"):
            parse_picks(content, "lift")

    def test_wrong_section_type_raises_for_treadle(self):
        liftplan_only = b"""
[WIF]
Version=1.1

[LIFTPLAN]
1=1,2
2=3,4
"""
        with pytest.raises(ValueError, match="TREADLING"):
            parse_picks(liftplan_only, "treadle")

    def test_weft_colors_none_when_no_color_sections(self):
        data = parse_picks(wif(), "treadle")
        assert all(c is None for c in data.weft_colors)
        assert len(data.weft_colors) == data.total_picks

    def test_malformed_weft_color_entry_skipped(self):
        """Non-numeric WEFT COLORS value must be silently skipped."""
        content = wif(
            "[COLOR PALETTE]\nRange=0,255\nForm=Decimal\n\n"
            "[COLOR TABLE]\n1=200,50,50\n\n"
            "[WEFT COLORS]\n1=not_a_number\n"
        )
        data = parse_picks(content, "treadle")
        assert isinstance(data, PickData)

    def test_weft_color_entry_with_valid_palette_idx(self):
        """Comma-prefixed WEFT COLORS values should parse the first integer."""
        content = wif(
            "[COLOR PALETTE]\nRange=0,255\nForm=Decimal\n\n"
            "[COLOR TABLE]\n1=200,50,50\n\n"
            "[WEFT COLORS]\n1=1\n2=1\n3=1\n4=1\n"
        )
        data = parse_picks(content, "treadle")
        assert data.weft_colors[0] == "#c83232"

    def test_weft_global_color_used_when_no_per_pick_section(self):
        """[WEFT] Color= is used as default when [WEFT COLORS] is absent."""
        content = wif("[COLOR PALETTE]\nRange=0,255\n\n[COLOR TABLE]\n3=0,0,255\n\n[WEFT]\nColor=3\nThreads=4\n")
        data = parse_picks(content, "treadle")
        assert all(c == "#0000ff" for c in data.weft_colors)

    def test_per_pick_colors_override_global_weft_default(self):
        """[WEFT COLORS] per-pick entries win over [WEFT] Color= global default."""
        content = wif(
            "[COLOR PALETTE]\nRange=0,255\n\n"
            "[COLOR TABLE]\n1=255,0,0\n3=0,0,255\n\n"
            "[WEFT]\nColor=3\nThreads=4\n\n"
            "[WEFT COLORS]\n1=1\n2=1\n"
        )
        data = parse_picks(content, "treadle")
        assert data.weft_colors[0] == "#ff0000"  # per-pick overrides global
        assert data.weft_colors[1] == "#ff0000"
        assert data.weft_colors[2] == "#0000ff"  # falls back to global
        assert data.weft_colors[3] == "#0000ff"


# ---------------------------------------------------------------------------
# Color table edge cases (_color_table internals via parse_picks)
# ---------------------------------------------------------------------------


class TestColorTableEdgeCases:
    def _wif_with_color_table(self, table_body: str) -> bytes:
        return wif(f"[COLOR PALETTE]\nRange=0,255\nForm=Decimal\n\n[COLOR TABLE]\n{table_body}\n")

    def test_short_rgb_entry_skipped(self):
        """Entry with fewer than 3 components must not raise."""
        content = self._wif_with_color_table("1=100,50\n2=200,100,50\n")
        data = parse_picks(content, "treadle")
        assert isinstance(data, PickData)

    def test_non_numeric_rgb_entry_skipped(self):
        """Entry with non-numeric RGB values must not raise."""
        content = self._wif_with_color_table("1=abc,def,ghi\n2=200,100,50\n")
        data = parse_picks(content, "treadle")
        assert isinstance(data, PickData)

    def test_valid_entry_after_bad_entry_is_parsed(self):
        """Good entries following a bad entry should still be included."""
        content = self._wif_with_color_table("1=bad\n2=200,100,50\n")
        data = parse_picks(content, "treadle")
        assert isinstance(data, PickData)

    def test_zero_division_scale_entry_skipped(self):
        """Scale of 0 on a non-255 palette causes ZeroDivisionError — must not raise."""
        content = wif("[COLOR PALETTE]\nRange=0,0\nForm=Decimal\n\n[COLOR TABLE]\n1=100,50,25\n")
        data = parse_picks(content, "treadle")
        assert isinstance(data, PickData)


# ---------------------------------------------------------------------------
# parse_picks — lift mode
# ---------------------------------------------------------------------------


class TestParsePicksLift:
    def _liftplan_wif(self, extra: str = "") -> bytes:
        return f"""
[WIF]
Version=1.1

[LIFTPLAN]
1=1,2
2=3,4
3=1,3

{extra}
""".strip().encode()

    def test_project_type(self):
        data = parse_picks(self._liftplan_wif(), "lift")
        assert data.project_type == "lift"

    def test_total_picks(self):
        data = parse_picks(self._liftplan_wif(), "lift")
        assert data.total_picks == 3

    def test_pick_values(self):
        data = parse_picks(self._liftplan_wif(), "lift")
        assert data.picks[0] == [1, 2]
        assert data.picks[1] == [3, 4]
        assert data.picks[2] == [1, 3]


# ---------------------------------------------------------------------------
# Weft color parsing
# ---------------------------------------------------------------------------

COLORS_SECTION = """
[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=255,0,0
2=0,255,0
3=0,0,255

[WEFT COLORS]
1=1
2=2
3=3
4=1
"""

LIFTPLAN_WITH_COLORS = f"""
[WIF]
Version=1.1

[LIFTPLAN]
1=1
2=2
3=3
4=4

{COLORS_SECTION}
""".strip().encode()


class TestWeftColors:
    def test_colors_resolved_to_hex(self):
        data = parse_picks(LIFTPLAN_WITH_COLORS, "lift")
        assert data.weft_colors[0] == "#ff0000"
        assert data.weft_colors[1] == "#00ff00"
        assert data.weft_colors[2] == "#0000ff"
        assert data.weft_colors[3] == "#ff0000"  # pick 4 reuses color 1

    def test_has_weft_colors_flag(self):
        data = parse_picks(LIFTPLAN_WITH_COLORS, "lift")
        assert any(c is not None for c in data.weft_colors)

    def test_missing_weft_color_entry_is_none(self):
        """Picks without a WEFT COLORS entry stay None."""
        content = """
[WIF]
Version=1.1

[LIFTPLAN]
1=1
2=2
3=3

[COLOR PALETTE]
Range=0,255

[COLOR TABLE]
1=255,0,0

[WEFT COLORS]
1=1
""".strip().encode()
        data = parse_picks(content, "lift")
        assert data.weft_colors[0] == "#ff0000"
        assert data.weft_colors[1] is None
        assert data.weft_colors[2] is None


# ---------------------------------------------------------------------------
# Color scale normalisation
# ---------------------------------------------------------------------------


class TestColorScale:
    def test_65535_scale_normalized_to_255(self):
        content = """
[WIF]
Version=1.1

[LIFTPLAN]
1=1

[COLOR PALETTE]
Range=0,65535

[COLOR TABLE]
1=65535,0,0

[WEFT COLORS]
1=1
""".strip().encode()
        data = parse_picks(content, "lift")
        assert data.weft_colors[0] == "#ff0000"

    def test_100_scale_normalized(self):
        """Scale=100 → values out of 100, should map to 0-255."""
        content = """
[WIF]
Version=1.1

[LIFTPLAN]
1=1

[COLOR PALETTE]
Range=0,100

[COLOR TABLE]
1=100,0,0

[WEFT COLORS]
1=1
""".strip().encode()
        data = parse_picks(content, "lift")
        assert data.weft_colors[0] == "#ff0000"

    def test_color_clamped_to_255(self):
        """Values beyond scale maximum are clamped, not rejected."""
        content = """
[WIF]
Version=1.1

[LIFTPLAN]
1=1

[COLOR PALETTE]
Range=0,255

[COLOR TABLE]
1=300,0,0

[WEFT COLORS]
1=1
""".strip().encode()
        data = parse_picks(content, "lift")
        assert data.weft_colors[0] == "#ff0000"

    def test_color_clamped_below_zero(self):
        content = """
[WIF]
Version=1.1

[LIFTPLAN]
1=1

[COLOR PALETTE]
Range=0,255

[COLOR TABLE]
1=-10,0,0

[WEFT COLORS]
1=1
""".strip().encode()
        data = parse_picks(content, "lift")
        assert data.weft_colors[0] == "#000000"


# ---------------------------------------------------------------------------
# Encoding fallback
# ---------------------------------------------------------------------------


class TestEncoding:
    def test_utf8_decoded(self):
        content = wif()
        assert parse_picks(content, "treadle").total_picks == 4

    def test_latin1_fallback(self):
        """WIF bytes that are not valid UTF-8 should decode via Latin-1."""
        text = """
[WIF]
Version=1.1

[TREADLING]
1=1
2=2
""".strip()
        # inject a Latin-1-only byte (0xe9 = é) into the source program value
        latin1_text = text.replace("1.1", "1.1\nSource Program=Caf\xe9Loom")
        content = latin1_text.encode("latin-1")
        data = parse_picks(content, "treadle")
        assert data.total_picks == 2


# ---------------------------------------------------------------------------
# compute_liftplan
# ---------------------------------------------------------------------------

TREADLING_AND_TIEUP = """
[WIF]
Version=1.1

[TREADLING]
1=1
2=2
3=1,2

[TIEUP]
1=1,3
2=2,4
""".strip().encode()


class TestComputeLiftplan:
    def test_returns_bytes(self):
        result = compute_liftplan(TREADLING_AND_TIEUP)
        assert isinstance(result, bytes)

    def test_liftplan_section_appended(self):
        result = compute_liftplan(TREADLING_AND_TIEUP)
        assert b"[LIFTPLAN]" in result

    def test_single_treadle_maps_to_tieup_shafts(self):
        result = compute_liftplan(TREADLING_AND_TIEUP)
        text = result.decode()
        # treadle 1 → shafts 1,3
        assert "1=1,3" in text

    def test_single_treadle_second_row(self):
        result = compute_liftplan(TREADLING_AND_TIEUP)
        text = result.decode()
        # treadle 2 → shafts 2,4
        assert "2=2,4" in text

    def test_multi_treadle_picks_union_shafts(self):
        result = compute_liftplan(TREADLING_AND_TIEUP)
        text = result.decode()
        # pick 3: treadles 1+2 → shafts 1,3 ∪ 2,4 = 1,2,3,4
        assert "3=1,2,3,4" in text

    def test_empty_pick_produces_empty_liftplan_entry(self):
        content = """
[WIF]
Version=1.1

[TREADLING]
1=1
2=

[TIEUP]
1=1,2
""".strip().encode()
        result = compute_liftplan(content)
        text = result.decode()
        assert "2=" in text

    def test_missing_treadling_raises(self):
        content = """
[WIF]
Version=1.1

[TIEUP]
1=1
""".strip().encode()
        with pytest.raises(ValueError, match="TREADLING"):
            compute_liftplan(content)

    def test_missing_tieup_raises(self):
        content = """
[WIF]
Version=1.1

[TREADLING]
1=1
""".strip().encode()
        with pytest.raises(ValueError, match="TIEUP"):
            compute_liftplan(content)

    def test_original_wif_content_preserved(self):
        """All original sections should still be present in the output."""
        result = compute_liftplan(TREADLING_AND_TIEUP)
        text = result.decode()
        assert "[TREADLING]" in text
        assert "[TIEUP]" in text
        assert "[WIF]" in text


# ---------------------------------------------------------------------------
# parse_threading
# ---------------------------------------------------------------------------

_THREADING_WIF = b"""[WIF]
Version=1.1
[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true
[WEAVING]
Shafts=4
Treadles=4
[WARP]
Threads=4
Units=Inches
Color=1
[WEFT]
Threads=4
Units=Inches
Color=2
[COLOR PALETTE]
Range=0,255
Form=Decimal
[COLOR TABLE]
1=200,50,50
2=50,50,200
[THREADING]
1=1
2=2
3=3
4=4
[TIEUP]
1=1
2=2
3=3
4=4
[TREADLING]
1=1
2=2
3=3
4=4
"""


class TestParseThreading:
    def test_returns_threading_data(self):
        result = parse_threading(_THREADING_WIF)
        assert isinstance(result, ThreadingData)

    def test_warp_thread_count(self):
        result = parse_threading(_THREADING_WIF)
        assert result.warp_thread_count == 4

    def test_threading_list_length(self):
        result = parse_threading(_THREADING_WIF)
        assert len(result.threading) == 4

    def test_threading_shafts_correct(self):
        result = parse_threading(_THREADING_WIF)
        assert result.threading[0] == [1]
        assert result.threading[1] == [2]

    def test_warp_colors_list_length(self):
        result = parse_threading(_THREADING_WIF)
        assert len(result.warp_colors) == 4

    def test_warp_color_is_hex(self):
        result = parse_threading(_THREADING_WIF)
        assert result.warp_colors[0] is not None
        assert result.warp_colors[0].startswith("#")

    def test_raises_without_threading_section(self):
        wif = b"[WIF]\nVersion=1.1\n"
        with pytest.raises(ValueError, match="THREADING"):
            parse_threading(wif)

    def test_latin1_encoding_fallback(self):
        text = _THREADING_WIF.decode("utf-8").replace("TestSuite", "Caf\xe9Loom")
        latin1_bytes = text.encode("latin-1")
        result = parse_threading(latin1_bytes)
        assert result.warp_thread_count == 4


# ---------------------------------------------------------------------------
# parse_tieup
# ---------------------------------------------------------------------------


class TestParseTieup:
    def test_returns_tieup_data(self):
        result = parse_tieup(_THREADING_WIF)
        assert isinstance(result, TieUpData)

    def test_num_treadles(self):
        result = parse_tieup(_THREADING_WIF)
        assert result.num_treadles == 4

    def test_tieup_list_length(self):
        result = parse_tieup(_THREADING_WIF)
        assert len(result.tieup) == 4

    def test_tieup_shaft_mapping(self):
        result = parse_tieup(_THREADING_WIF)
        assert result.tieup[0] == [1]
        assert result.tieup[1] == [2]

    def test_raises_without_tieup_section(self):
        wif = b"[WIF]\nVersion=1.1\n"
        with pytest.raises(ValueError, match="TIEUP"):
            parse_tieup(wif)

    def test_latin1_encoding_fallback(self):
        text = _THREADING_WIF.decode("utf-8").replace("TestSuite", "Caf\xe9Loom")
        latin1_bytes = text.encode("latin-1")
        result = parse_tieup(latin1_bytes)
        assert result.num_treadles == 4

    def test_output_parseable_as_liftplan(self):
        """The generated liftplan should be readable by parse_picks."""
        result = compute_liftplan(TREADLING_AND_TIEUP)
        data = parse_picks(result, "lift")
        assert data.total_picks == 3
        assert sorted(data.picks[2]) == [1, 2, 3, 4]

    def test_latin1_input_produces_utf8_output(self):
        latin1_content = (
            TREADLING_AND_TIEUP.decode().replace("Version=1.1", "Version=1.1\nSource Program=Caf\xe9").encode("latin-1")
        )
        result = compute_liftplan(latin1_content)
        assert b"[LIFTPLAN]" in result


# ---------------------------------------------------------------------------
# extract_measurements
# ---------------------------------------------------------------------------


def _mwif(warp: str = "", weft: str = "") -> bytes:
    sections = ["[WIF]\nVersion=1.1\n\n[WEAVING]\nShafts=4\nTreadles=4"]
    if warp:
        sections.append(f"[WARP]\n{warp}")
    if weft:
        sections.append(f"[WEFT]\n{weft}")
    return "\n\n".join(sections).encode()


class TestExtractMeasurements:
    def test_returns_dict(self):
        result = extract_measurements(_mwif())
        assert isinstance(result, dict)

    def test_empty_when_no_warp_section(self):
        result = extract_measurements(b"[WIF]\nVersion=1.1")
        assert result == {}

    def test_warp_length_inches_normalized_to_cm(self):
        result = extract_measurements(_mwif(warp="Units=Inches\nLength=100"))
        assert pytest.approx(result["warp_length"], rel=1e-4) == 254.0
        assert result["warp_length_original"] == 100.0
        assert result["warp_length_unit"] == "in"

    def test_warp_length_centimeters_unchanged(self):
        result = extract_measurements(_mwif(warp="Units=Centimeters\nLength=200"))
        assert pytest.approx(result["warp_length"]) == 200.0
        assert result["warp_length_unit"] == "cm"

    def test_warp_length_decipoints_normalized(self):
        # 720 decipoints = 1 inch = 2.54 cm
        result = extract_measurements(_mwif(warp="Units=Decipoints\nLength=720"))
        assert pytest.approx(result["warp_length"], rel=1e-3) == 2.54
        assert result["warp_length_unit"] == "dp"

    def test_default_unit_is_inches_when_absent(self):
        result = extract_measurements(_mwif(warp="Length=10"))
        assert pytest.approx(result["warp_length"], rel=1e-4) == 25.4
        assert result["warp_length_unit"] == "in"

    def test_warp_spacing_extracted(self):
        result = extract_measurements(_mwif(warp="Units=Inches\nSpacing=0.2"))
        assert pytest.approx(result["warp_spacing"], rel=1e-4) == 0.508
        assert result["warp_spacing_original"] == 0.2
        assert result["warp_spacing_unit"] == "in"

    def test_weft_spacing_extracted(self):
        result = extract_measurements(_mwif(weft="Units=Centimeters\nSpacing=0.3"))
        assert pytest.approx(result["weft_spacing"]) == 0.3
        assert result["weft_spacing_unit"] == "cm"

    def test_warp_length_absent_key_missing(self):
        result = extract_measurements(_mwif(warp="Units=Inches\nSpacing=0.2"))
        assert "warp_length" not in result
        assert "warp_spacing" in result

    def test_weft_length_inches_normalized(self):
        result = extract_measurements(_mwif(weft="Units=Inches\nLength=50"))
        assert pytest.approx(result["weft_length"], rel=1e-4) == 127.0
        assert result["weft_length_original"] == 50.0
        assert result["weft_length_unit"] == "in"

    def test_weft_length_centimeters_unchanged(self):
        result = extract_measurements(_mwif(weft="Units=Centimeters\nLength=300"))
        assert pytest.approx(result["weft_length"]) == 300.0
        assert result["weft_length_unit"] == "cm"

    def test_weft_length_absent_key_missing(self):
        result = extract_measurements(_mwif(weft="Units=Inches\nSpacing=0.2"))
        assert "weft_length" not in result
        assert "weft_spacing" in result

    def test_non_numeric_length_skipped(self):
        result = extract_measurements(_mwif(warp="Units=Inches\nLength=not_a_number"))
        assert "warp_length" not in result

    def test_warp_and_weft_different_units(self):
        result = extract_measurements(_mwif(warp="Units=Inches\nLength=100", weft="Units=Centimeters\nSpacing=0.5"))
        assert result["warp_length_unit"] == "in"
        assert result["weft_spacing_unit"] == "cm"
        assert pytest.approx(result["weft_spacing"]) == 0.5

    def test_invalid_wif_bytes_returns_empty(self):
        result = extract_measurements(b"\xff\xfe invalid binary \x00")
        assert isinstance(result, dict)

    def test_latin1_wif_parsed(self):
        latin1_wif = "[WIF]\nVersion=1.1\n\n[WARP]\nUnits=Inches\nLength=50\n".encode("latin-1")
        result = extract_measurements(latin1_wif)
        assert pytest.approx(result["warp_length"], rel=1e-4) == 127.0


# ---------------------------------------------------------------------------
# extract_colors
# ---------------------------------------------------------------------------


def _cwif(
    table_body: str = "",
    palette: str = "Range=0,255\nForm=Decimal",
    weft_colors: str = "",
    warp_colors: str = "",
    weft_default: str = "",
    warp_default: str = "",
) -> bytes:
    """Build a minimal WIF for color extraction tests.

    table_body: content of [COLOR TABLE]
    weft_colors: content of [WEFT COLORS] (per-pick palette index refs)
    warp_colors: content of [WARP COLORS] (per-thread palette index refs)
    weft_default: value for [WEFT] Color= key
    warp_default: value for [WARP] Color= key
    """
    sections = [f"[WIF]\nVersion=1.1\n\n[COLOR PALETTE]\n{palette}"]
    if table_body:
        sections.append(f"[COLOR TABLE]\n{table_body}")
    if weft_colors:
        sections.append(f"[WEFT COLORS]\n{weft_colors}")
    if warp_colors:
        sections.append(f"[WARP COLORS]\n{warp_colors}")
    if weft_default or warp_default:
        weft_line = f"Color={weft_default}" if weft_default else ""
        warp_line = f"Color={warp_default}" if warp_default else ""
        if weft_line:
            sections.append(f"[WEFT]\n{weft_line}")
        if warp_line:
            sections.append(f"[WARP]\n{warp_line}")
    return "\n\n".join(sections).encode()


class TestExtractColors:
    def test_returns_list(self):
        result = extract_colors(_cwif("1=255,0,0", weft_colors="1=1"))
        assert isinstance(result, list)

    def test_empty_when_no_color_table(self):
        result = extract_colors(b"[WIF]\nVersion=1.1")
        assert result == []

    def test_empty_when_no_references_in_design(self):
        """Color table exists but nothing in the design references any index."""
        result = extract_colors(_cwif("1=255,0,0\n2=0,255,0"))
        assert result == []

    def test_single_color_via_weft_colors(self):
        result = extract_colors(_cwif("1=255,0,0", weft_colors="1=1"))
        assert len(result) == 1
        c = result[0]
        assert c["index"] == 1
        assert c["r"] == 255
        assert c["hex"] == "#ff0000"

    def test_single_color_via_global_weft_default(self):
        result = extract_colors(_cwif("2=0,255,0", weft_default="2"))
        assert len(result) == 1
        assert result[0]["index"] == 2
        assert result[0]["hex"] == "#00ff00"

    def test_single_color_via_global_warp_default(self):
        result = extract_colors(_cwif("3=0,0,255", warp_default="3"))
        assert len(result) == 1
        assert result[0]["hex"] == "#0000ff"

    def test_single_color_via_warp_colors(self):
        result = extract_colors(_cwif("4=128,0,128", warp_colors="1=4"))
        assert len(result) == 1
        assert result[0]["index"] == 4

    def test_unreferenced_color_excluded(self):
        """Color 2 is in the table but not referenced — must not appear."""
        result = extract_colors(_cwif("1=255,0,0\n2=0,255,0", weft_colors="1=1"))
        assert len(result) == 1
        assert result[0]["index"] == 1

    def test_multiple_referenced_colors_sorted(self):
        result = extract_colors(_cwif("3=0,0,255\n1=255,0,0\n2=0,255,0", weft_colors="1=3\n2=1\n3=2"))
        assert [c["index"] for c in result] == [1, 2, 3]
        assert result[0]["hex"] == "#ff0000"
        assert result[1]["hex"] == "#00ff00"
        assert result[2]["hex"] == "#0000ff"

    def test_scale_65535_normalized_to_255(self):
        result = extract_colors(_cwif("1=65535,0,0", palette="Range=0,65535", weft_colors="1=1"))
        assert result[0]["r"] == 255
        assert result[0]["hex"] == "#ff0000"

    def test_scale_100_normalized(self):
        result = extract_colors(_cwif("1=100,0,0", palette="Range=0,100", weft_colors="1=1"))
        assert result[0]["r"] == 255
        assert result[0]["hex"] == "#ff0000"

    def test_values_clamped_below_zero(self):
        result = extract_colors(_cwif("1=-10,0,0", weft_colors="1=1"))
        assert result[0]["r"] == 0

    def test_values_clamped_above_255(self):
        result = extract_colors(_cwif("1=300,0,0", weft_colors="1=1"))
        assert result[0]["r"] == 255

    def test_short_rgb_entry_skipped(self):
        result = extract_colors(_cwif("1=100,50\n2=200,100,50", weft_colors="1=1\n2=2"))
        assert len(result) == 1
        assert result[0]["index"] == 2

    def test_non_numeric_entry_skipped(self):
        result = extract_colors(_cwif("1=abc,def,ghi\n2=0,255,0", weft_colors="1=1\n2=2"))
        assert len(result) == 1
        assert result[0]["hex"] == "#00ff00"

    def test_invalid_bytes_returns_empty(self):
        result = extract_colors(b"\xff\xfe not a wif")
        assert result == []

    def test_all_fields_present(self):
        result = extract_colors(_cwif("1=128,64,32", weft_colors="1=1"))
        c = result[0]
        assert set(c.keys()) == {"index", "r", "g", "b", "hex"}
        assert c["hex"] == f"#{128:02x}{64:02x}{32:02x}"

    def test_latin1_wif_parsed(self):
        latin1_wif = (
            "[WIF]\nVersion=1.1\n\n[COLOR PALETTE]\nRange=0,255\n\n[COLOR TABLE]\n1=255,0,0\n\n[WEFT COLORS]\n1=1\n"
        ).encode("latin-1")
        result = extract_colors(latin1_wif)
        assert len(result) == 1
        assert result[0]["hex"] == "#ff0000"


def _stats_wif(weft_colors_section: str = "", color_table: str = "", liftplan: str = "") -> bytes:
    """Build a minimal WIF for weft_color_stats tests."""
    parts = ["[WIF]\nVersion=1.1\n\n[COLOR PALETTE]\nRange=0,255\n"]
    if color_table:
        parts.append(f"[COLOR TABLE]\n{color_table}\n")
    if liftplan:
        parts.append(f"[LIFTPLAN]\n{liftplan}\n")
    else:
        parts.append("[TREADLING]\n1=1\n2=2\n3=1\n4=2\n\n[TIEUP]\n1=1\n2=2\n")
    if weft_colors_section:
        parts.append(f"[WEFT COLORS]\n{weft_colors_section}\n")
    return "".join(parts).encode("utf-8")


class TestExtractWeftColorStats:
    def test_returns_empty_without_picks_section(self):
        result = extract_weft_color_stats(b"[WIF]\nVersion=1.1\n")
        assert result == []

    def test_returns_empty_without_color_assignments(self):
        result = extract_weft_color_stats(_stats_wif())
        assert result == []

    def test_single_color_all_picks(self):
        result = extract_weft_color_stats(
            _stats_wif(
                color_table="1=255,0,0\n",
                weft_colors_section="1=1\n2=1\n3=1\n4=1\n",
            )
        )
        assert len(result) == 1
        assert result[0]["hex"] == "#ff0000"
        assert result[0]["count"] == 4
        assert result[0]["percentage"] == 100.0

    def test_two_colors_counts_and_percentages(self):
        result = extract_weft_color_stats(
            _stats_wif(
                color_table="1=255,0,0\n2=0,0,255\n",
                weft_colors_section="1=1\n2=1\n3=2\n4=2\n",
            )
        )
        assert len(result) == 2
        by_hex = {r["hex"]: r for r in result}
        assert by_hex["#ff0000"]["count"] == 2
        assert by_hex["#0000ff"]["count"] == 2
        assert by_hex["#ff0000"]["percentage"] == 50.0

    def test_sorted_by_count_descending(self):
        result = extract_weft_color_stats(
            _stats_wif(
                color_table="1=255,0,0\n2=0,0,255\n",
                weft_colors_section="1=1\n2=1\n3=1\n4=2\n",
            )
        )
        assert result[0]["count"] >= result[1]["count"]

    def test_liftplan_preferred_over_treadling(self):
        w = _stats_wif(
            color_table="1=255,0,0\n",
            liftplan="1=1\n2=1\n",
            weft_colors_section="1=1\n2=1\n",
        )
        result = extract_weft_color_stats(w)
        assert len(result) == 1
        assert result[0]["count"] == 2

    def test_invalid_bytes_returns_empty(self):
        assert extract_weft_color_stats(b"\xff\xfe invalid") == []

    def test_empty_picks_returns_empty(self):
        # Covers line 266: total == 0 → return []
        # WIF with TREADLING section but no entries → 0 picks
        content = b"[WIF]\nVersion=1.1\n\n[COLOR PALETTE]\nRange=0,255\n\n[COLOR TABLE]\n1=255,0,0\n\n[TREADLING]\n"
        result = extract_weft_color_stats(content)
        assert result == []


# ---------------------------------------------------------------------------
# extract_warp_color_stats
# ---------------------------------------------------------------------------


def _warp_stats_wif(
    num_threads: int = 0,
    warp_colors_section: str = "",
    color_table: str = "",
    warp_default: str = "",
) -> bytes:
    parts = ["[WIF]\nVersion=1.1\n\n[COLOR PALETTE]\nRange=0,255\n"]
    if num_threads:
        parts.append(f"[WEAVING]\nWarp threads={num_threads}\n")
    if color_table:
        parts.append(f"[COLOR TABLE]\n{color_table}\n")
    if warp_colors_section:
        parts.append(f"[WARP COLORS]\n{warp_colors_section}\n")
    if warp_default:
        parts.append(f"[WARP]\nColor={warp_default}\n")
    return "".join(parts).encode("utf-8")


class TestExtractWarpColorStats:
    def test_returns_empty_without_color_table(self):
        result = extract_warp_color_stats(b"[WIF]\nVersion=1.1\n")
        assert result == []

    def test_returns_empty_without_thread_count_or_warp_colors(self):
        result = extract_warp_color_stats(_warp_stats_wif(color_table="1=255,0,0\n"))
        assert result == []

    def test_single_color_all_threads_via_default(self):
        result = extract_warp_color_stats(_warp_stats_wif(num_threads=4, color_table="1=255,0,0\n", warp_default="1"))
        assert len(result) == 1
        assert result[0]["hex"] == "#ff0000"
        assert result[0]["count"] == 4
        assert result[0]["percentage"] == 100.0

    def test_per_thread_colors_override_default(self):
        result = extract_warp_color_stats(
            _warp_stats_wif(
                num_threads=4,
                color_table="1=255,0,0\n2=0,0,255\n",
                warp_colors_section="1=1\n2=1\n3=2\n4=2\n",
            )
        )
        by_hex = {r["hex"]: r for r in result}
        assert by_hex["#ff0000"]["count"] == 2
        assert by_hex["#0000ff"]["count"] == 2

    def test_sorted_by_count_descending(self):
        result = extract_warp_color_stats(
            _warp_stats_wif(
                num_threads=4,
                color_table="1=255,0,0\n2=0,0,255\n",
                warp_colors_section="1=1\n2=1\n3=1\n4=2\n",
            )
        )
        assert result[0]["count"] >= result[1]["count"]

    def test_thread_count_inferred_from_warp_colors_max_key(self):
        """No [WEAVING] section — thread count derived from max key in WARP COLORS."""
        result = extract_warp_color_stats(
            _warp_stats_wif(
                color_table="1=255,0,0\n",
                warp_colors_section="1=1\n2=1\n3=1\n",
            )
        )
        assert len(result) == 1
        assert result[0]["count"] == 3

    def test_thread_count_inferred_from_threading_section(self):
        """No [WEAVING] or [WARP COLORS] — thread count from max [THREADING] key."""
        content = (
            b"[WIF]\nVersion=1.1\n\n"
            b"[COLOR PALETTE]\nRange=0,255\n\n"
            b"[COLOR TABLE]\n1=255,0,0\n\n"
            b"[WARP]\nColor=1\n\n"
            b"[THREADING]\n1=1\n2=2\n3=1\n4=2\n"
        )
        result = extract_warp_color_stats(content)
        assert len(result) == 1
        assert result[0]["count"] == 4

    def test_percentages_sum_to_100(self):
        result = extract_warp_color_stats(
            _warp_stats_wif(
                num_threads=3,
                color_table="1=255,0,0\n2=0,255,0\n",
                warp_colors_section="1=1\n2=1\n3=2\n",
            )
        )
        total = sum(r["percentage"] for r in result)
        assert pytest.approx(total, abs=0.2) == 100.0

    def test_invalid_bytes_returns_empty(self):
        assert extract_warp_color_stats(b"\xff\xfe invalid") == []

    def test_bad_warp_color_default_is_ignored(self):
        # Covers lines 188-189: Color= is non-numeric → exception caught, default stays None
        content = _warp_stats_wif(
            num_threads=2,
            color_table="1=255,0,0\n",
            warp_default="notanumber",
        )
        result = extract_warp_color_stats(content)
        assert result == []

    def test_bad_warp_colors_value_is_skipped(self):
        # Covers lines 196-197: WARP COLORS value non-numeric → ValueError caught
        content = (
            b"[WIF]\nVersion=1.1\n\n"
            b"[WEAVING]\nShafts=2\nTreadles=2\nWarp threads=2\n\n"
            b"[COLOR PALETTE]\nRange=0,255\n\n"
            b"[COLOR TABLE]\n1=255,0,0\n\n"
            b"[WARP COLORS]\n1=notanumber\n2=1\n"
        )
        result = extract_warp_color_stats(content)
        assert isinstance(result, list)

    def test_threading_section_bad_keys_exception_caught(self):
        # Covers lines 211-212: non-integer THREADING keys → max() raises, caught
        content = (
            b"[WIF]\nVersion=1.1\n\n"
            b"[COLOR PALETTE]\nRange=0,255\n\n"
            b"[COLOR TABLE]\n1=255,0,0\n\n"
            b"[WARP]\nColor=1\n\n"
            b"[THREADING]\nbadkey=1\n"
        )
        result = extract_warp_color_stats(content)
        assert result == []

    def test_threads_without_color_in_table_returns_empty(self):
        # Covers lines 219-220 (continue) and 223-224 (return []):
        # no default color + no WARP COLORS → all threads get hex_color=None → empty
        content = (
            b"[WIF]\nVersion=1.1\n\n"
            b"[WEAVING]\nShafts=2\nTreadles=2\nWarp threads=2\n\n"
            b"[COLOR PALETTE]\nRange=0,255\n\n"
            b"[COLOR TABLE]\n1=255,0,0\n"
        )
        result = extract_warp_color_stats(content)
        assert result == []


# ---------------------------------------------------------------------------
# Edge cases: extract_colors exception handlers
# ---------------------------------------------------------------------------


class TestExtractColorsEdgeCases:
    def test_bad_warp_color_default_is_silently_ignored(self):
        # Covers lines 118-119: Color= non-numeric → exception caught
        content = wif(
            "[WARP]\nThreads=4\nColor=notanumber\n\n[COLOR TABLE]\n1=255,0,0\n\n[COLOR PALETTE]\nRange=0,255\n"
        )
        result = extract_colors(content)
        assert isinstance(result, list)

    def test_bad_warp_colors_value_is_skipped(self):
        # Covers lines 126-127: WARP COLORS non-numeric → ValueError caught, continue
        content = wif(
            "[WARP]\nThreads=2\nColor=1\n\n"
            "[WARP COLORS]\n1=notanumber\n\n"
            "[COLOR TABLE]\n1=255,0,0\n\n"
            "[COLOR PALETTE]\nRange=0,255\n"
        )
        result = extract_colors(content)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Edge cases: parse_threading exception handlers + fallbacks
# ---------------------------------------------------------------------------


class TestParseThreadingEdgeCases:
    def test_latin1_encoded_wif_is_parsed(self):
        # Covers lines 308-309: UnicodeDecodeError triggers latin-1 fallback
        text = "[WIF]\nVersion=1.1\n\n[THREADING]\n1=1\n2=2\n\n[TIEUP]\n1=1\n2=2\n"
        wif_bytes = (text + "\n; caf\xe9\n").encode("latin-1")
        result = parse_threading(wif_bytes)
        assert result.warp_thread_count == 2

    def test_bad_warp_default_color_is_ignored(self):
        # Covers lines 335-336: WARP Color= non-numeric → exception caught
        content = wif(
            "[THREADING]\n1=1\n2=2\n3=3\n4=4\n\n"
            "[WARP]\nThreads=4\nColor=notanumber\n\n"
            "[COLOR TABLE]\n1=255,0,0\n\n"
            "[COLOR PALETTE]\nRange=0,255\n"
        )
        result = parse_threading(content)
        assert result.warp_thread_count == 4

    def test_bad_warp_colors_entry_is_skipped(self):
        # Covers lines 340-344: WARP COLORS non-numeric → ValueError caught, continue
        content = wif(
            "[THREADING]\n1=1\n2=2\n3=3\n4=4\n\n"
            "[WARP]\nThreads=4\nColor=1\n\n"
            "[WARP COLORS]\n1=notanumber\n2=1\n\n"
            "[COLOR TABLE]\n1=255,0,0\n\n"
            "[COLOR PALETTE]\nRange=0,255\n"
        )
        result = parse_threading(content)
        assert result.warp_thread_count == 4

    def test_no_color_table_returns_empty_color_names(self):
        # Covers line 465: _color_name_table early-returns when no COLOR TABLE
        content = wif("[THREADING]\n1=1\n2=2\n3=3\n4=4\n")
        result = parse_threading(content)
        assert result.color_names == {}

    def test_color_name_table_extracts_name_token(self):
        # Covers lines 473-476: non-numeric token in COLOR TABLE value → name extracted
        content = wif(
            "[THREADING]\n1=1\n2=2\n3=3\n4=4\n\n[COLOR TABLE]\n1=255,0,0,Red\n\n[COLOR PALETTE]\nRange=0,255\n"
        )
        result = parse_threading(content)
        assert "Red" in result.color_names.values()

    def test_color_name_table_bad_key_is_skipped(self):
        # Covers line 477: non-integer COLOR TABLE key → outer except catches, continue
        content = wif(
            "[THREADING]\n1=1\n2=2\n3=3\n4=4\n\n"
            "[COLOR TABLE]\nbadkey=255,0,0\n1=0,255,0\n\n"
            "[COLOR PALETTE]\nRange=0,255\n"
        )
        result = parse_threading(content)
        assert isinstance(result.color_names, dict)


# ---------------------------------------------------------------------------
# Edge cases: parse_tieup — latin-1 fallback + empty section raises
# ---------------------------------------------------------------------------


class TestParseTieupEdgeCases:
    def test_latin1_encoded_wif_is_parsed(self):
        # Covers lines 373-374: UnicodeDecodeError triggers latin-1 fallback
        text = "[WIF]\nVersion=1.1\n\n[TIEUP]\n1=1\n2=2\n\n; caf\xe9\n"
        wif_bytes = text.encode("latin-1")
        result = parse_tieup(wif_bytes)
        assert result.num_treadles >= 2

    def test_empty_tieup_section_raises(self):
        # Covers line 385: empty TIEUP → raises ValueError
        content = b"[WIF]\nVersion=1.1\n\n[TIEUP]\n"
        with pytest.raises(ValueError, match="empty"):
            parse_tieup(content)
