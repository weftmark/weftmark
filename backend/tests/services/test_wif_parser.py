"""
Tests for app.services.wif_parser.

Covers: pick parsing (treadle + lift), weft color extraction,
color scale normalisation, liftplan computation, encoding fallback.
"""

import pytest

from app.services.wif_parser import PickData, compute_liftplan, parse_picks

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
