"""
Tests for app.services.rendering.

WIFReader requires a real filesystem file, so load_draft uses a temp file
internally.  These tests verify basic parse correctness and that render
output is valid PNG bytes.

A full PyWeaving-compatible WIF requires: [WIF] with Date, [CONTENTS],
[WEAVING] with Rising Shed, [WARP]/[WEFT] with Threads+Units+Color,
[COLOR TABLE], [THREADING], [TIEUP], [TREADLING].
"""

import sys
from pathlib import Path

import pytest

from app.services.rendering import (
    DRAWDOWN_SCALE,
    load_draft,
    render_drawdown_only,
    render_drawdown_preview,
    render_drawdown_tile,
    render_full_draft,
    render_full_draft_liftplan,
    safe_preview_scale,
)

# Real-world liftplan WIF that declares Treadles=8 as metadata (TempoWeave Designer output).
_SAMPLES_DIR = Path(__file__).parents[3] / "docs" / "samples"
_SHADOW_FLOWERS_WIF = _SAMPLES_DIR / "Shadow_flowers~assembly-LP.wif"

# ---------------------------------------------------------------------------
# Minimal valid WIF fixture
# ---------------------------------------------------------------------------

MINIMAL_WIF = b"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

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

EIGHT_SHAFT_WIF = b"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts=8
Treadles=10
Rising Shed=true

[WARP]
Threads=8
Units=Inches
Color=1

[WEFT]
Threads=8
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
5=5
6=6
7=7
8=8

[TIEUP]
1=1
2=2
3=3
4=4
5=5
6=6
7=7
8=8

[TREADLING]
1=1
2=2
3=3
4=4
5=5
6=6
7=7
8=8
"""


# ---------------------------------------------------------------------------
# Pillow API compatibility
# ---------------------------------------------------------------------------


class TestPillowCompat:
    def test_textbbox_available(self):
        """The vendored renderer uses textbbox (Pillow ≥8); verify it exists."""
        from PIL.ImageDraw import ImageDraw

        assert hasattr(ImageDraw, "textbbox"), "Pillow textbbox missing — upgrade Pillow"


# ---------------------------------------------------------------------------
# load_draft
# ---------------------------------------------------------------------------


class TestLoadDraft:
    def test_returns_draft_object(self):
        from app.weaving import Draft

        draft = load_draft(MINIMAL_WIF)
        assert isinstance(draft, Draft)

    def test_four_shaft_draft(self):
        draft = load_draft(MINIMAL_WIF)
        assert len(draft.shafts) == 4

    def test_eight_shaft_draft(self):
        draft = load_draft(EIGHT_SHAFT_WIF)
        assert len(draft.shafts) == 8

    def test_warp_threads_loaded(self):
        draft = load_draft(MINIMAL_WIF)
        assert len(draft.warp) == 4

    def test_weft_threads_loaded(self):
        draft = load_draft(MINIMAL_WIF)
        assert len(draft.weft) == 4

    def test_rising_shed_set(self):
        draft = load_draft(MINIMAL_WIF)
        assert draft.rising_shed is True

    def test_invalid_wif_raises(self):
        with pytest.raises(Exception):
            load_draft(b"this is not a wif file at all")

    @pytest.mark.skipif(
        sys.platform == "win32", reason="configparser uses cp1252 on Windows, which reads Latin-1 without error"
    )
    def test_latin1_encoded_wif_raises(self):
        """load_draft uses configparser which opens files as UTF-8; Latin-1
        bytes raise UnicodeDecodeError.  Callers must normalise encoding first
        (wif_parser handles this; rendering does not)."""
        latin1_wif = MINIMAL_WIF.decode().replace("TestSuite", "Caf\xe9Loom").encode("latin-1")
        with pytest.raises(Exception):
            load_draft(latin1_wif)


# ---------------------------------------------------------------------------
# render_full_draft
# ---------------------------------------------------------------------------


class TestRenderFullDraft:
    def test_returns_bytes(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft)
        assert isinstance(result, bytes)

    def test_output_is_png(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft)
        assert result[:4] == b"\x89PNG", "Output is not a valid PNG"

    def test_non_empty_output(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft)
        assert len(result) > 100

    def test_scale_affects_output_size(self):
        draft = load_draft(MINIMAL_WIF)
        small = render_full_draft(draft, scale=4)
        large = render_full_draft(draft, scale=10)
        assert len(large) > len(small)

    def test_scale_1_does_not_raise(self):
        """paint_fill_marker patch: scale < 4 must not raise 'x1 >= x0'."""
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft, scale=1)
        assert result[:4] == b"\x89PNG"

    def test_scale_2_does_not_raise(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft, scale=2)
        assert result[:4] == b"\x89PNG"

    def test_eight_shaft_renders(self):
        draft = load_draft(EIGHT_SHAFT_WIF)
        result = render_full_draft(draft, scale=4)
        assert result[:4] == b"\x89PNG"

    def test_default_scale_produces_png(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft)
        assert result[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# safe_preview_scale
# ---------------------------------------------------------------------------


class TestSafePreviewScale:
    def test_small_draft_unchanged(self):
        draft = load_draft(MINIMAL_WIF)  # 4 warp × 4 weft — tiny
        assert safe_preview_scale(draft, desired_scale=10) == 10

    def test_large_draft_reduced(self):
        """A draft large enough to exceed the pixel cap must return a scale below desired."""
        # Build a WIF with many warp/weft threads to simulate a large draft
        big_wif = _make_wif(warp=500, weft=2000, shafts=4)
        draft = load_draft(big_wif)
        result = safe_preview_scale(draft, desired_scale=10)
        # 500 * 2000 * 10^2 = 100M pixels — right at the limit; should be <= 10
        assert result <= 10
        # And total pixels at returned scale should be under the cap
        total = 500 * (2000 + 6 + 4) * result * result
        assert total <= 100_000_000

    def test_very_large_draft_capped(self):
        """Draft similar to Waffle 1 (1285 warp × 3058 weft) must render at reduced scale."""
        big_wif = _make_wif(warp=1285, weft=3058, shafts=8)
        draft = load_draft(big_wif)
        result = safe_preview_scale(draft, desired_scale=10)
        assert result < 10  # must reduce
        total = 1285 * (3058 + 6 + 8) * result * result
        assert total <= 100_000_000

    def test_returns_at_least_one(self):
        """Even an enormous draft must return scale >= 1."""
        big_wif = _make_wif(warp=10000, weft=50000, shafts=32)
        draft = load_draft(big_wif)
        assert safe_preview_scale(draft, desired_scale=10) >= 1

    def test_render_full_draft_large_does_not_raise(self):
        """render_full_draft on a large draft must not raise DecompressionBombError."""
        big_wif = _make_wif(warp=1285, weft=3058, shafts=8)
        draft = load_draft(big_wif)
        result = render_full_draft(draft)
        assert result[:4] == b"\x89PNG"


def _make_wif(warp: int, weft: int, shafts: int) -> bytes:
    """Build a minimal valid WIF with the given thread counts."""
    threading = "\n".join(f"{i}={((i - 1) % shafts) + 1}" for i in range(1, warp + 1))
    treadling = "\n".join(f"{i}={((i - 1) % shafts) + 1}" for i in range(1, weft + 1))
    tieup = "\n".join(f"{i}={i}" for i in range(1, shafts + 1))
    return f"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts={shafts}
Treadles={shafts}
Rising Shed=true

[WARP]
Threads={warp}
Units=Inches
Color=1

[WEFT]
Threads={weft}
Units=Inches
Color=2

[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=200,50,50
2=50,50,200

[THREADING]
{threading}

[TIEUP]
{tieup}

[TREADLING]
{treadling}
""".encode()


# ---------------------------------------------------------------------------
# render_full_draft_liftplan
# ---------------------------------------------------------------------------


class TestRenderFullDraftLiftplan:
    def test_returns_bytes(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft_liftplan(draft)
        assert isinstance(result, bytes)

    def test_output_is_png(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft_liftplan(draft)
        assert result[:4] == b"\x89PNG"

    def test_non_empty_output(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft_liftplan(draft)
        assert len(result) > 100

    def test_differs_from_standard_render(self):
        """Liftplan view renders differently from the standard treadle view."""
        draft = load_draft(MINIMAL_WIF)
        standard = render_full_draft(draft, scale=4)
        liftplan = render_full_draft_liftplan(draft, scale=4)
        assert standard != liftplan

    def test_scale_affects_output_size(self):
        draft = load_draft(MINIMAL_WIF)
        small = render_full_draft_liftplan(draft, scale=4)
        large = render_full_draft_liftplan(draft, scale=10)
        assert len(large) > len(small)

    def test_eight_shaft_renders(self):
        draft = load_draft(EIGHT_SHAFT_WIF)
        result = render_full_draft_liftplan(draft, scale=4)
        assert result[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# render_drawdown_only
# ---------------------------------------------------------------------------


class TestRenderDrawdownOnly:
    def test_returns_tuple(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_drawdown_only(draft)
        assert isinstance(result, tuple) and len(result) == 3

    def test_first_element_is_png(self):
        draft = load_draft(MINIMAL_WIF)
        png, _, _ = render_drawdown_only(draft)
        assert png[:4] == b"\x89PNG"

    def test_second_element_is_weft_count(self):
        draft = load_draft(MINIMAL_WIF)
        _, total_rows, _ = render_drawdown_only(draft)
        assert total_rows == len(draft.weft)

    def test_third_element_is_scale_used(self):
        draft = load_draft(MINIMAL_WIF)
        _, _, scale_used = render_drawdown_only(draft, scale=10)
        assert isinstance(scale_used, int) and scale_used == 10

    def test_drawdown_scale_constant_is_20(self):
        assert DRAWDOWN_SCALE == 20

    def test_dimensions_match_warp_weft(self):
        import io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, total_rows, scale_used = render_drawdown_only(draft, scale=scale)
        img = Image.open(io.BytesIO(png))
        assert img.width == len(draft.warp) * scale_used
        assert img.height == len(draft.weft) * scale_used
        assert total_rows == len(draft.weft)

    def test_adaptive_scale_reduces_for_large_draft(self, monkeypatch):
        """Scale is reduced automatically when draft exceeds render limits."""
        from app.config import Settings

        draft = load_draft(MINIMAL_WIF)
        # Force a very small render limit so the default scale=20 would exceed it.
        tiny_settings = Settings(render_max_width=40, render_max_height=40)
        monkeypatch.setattr("app.services.rendering.get_settings", lambda: tiny_settings)
        _, _, scale_used = render_drawdown_only(draft)
        warp = len(draft.warp)
        weft = len(draft.weft)
        assert scale_used * warp <= 40
        assert scale_used * weft <= 40
        assert scale_used >= 1

    def test_eight_shaft_renders(self):
        draft = load_draft(EIGHT_SHAFT_WIF)
        png, total_rows, _ = render_drawdown_only(draft, scale=4)
        assert png[:4] == b"\x89PNG"
        assert total_rows == len(draft.weft)

    def test_empty_draft_raises_value_error(self):
        draft = load_draft(MINIMAL_WIF)
        draft.warp = []
        with pytest.raises(ValueError, match="no drawdown data"):
            render_drawdown_only(draft)


# ---------------------------------------------------------------------------
# Real-world liftplan WIF with stale Treadles= metadata (#266)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# render_drawdown_tile
# ---------------------------------------------------------------------------


class TestRenderDrawdownTile:
    def test_returns_tuple_of_five(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_drawdown_tile(draft, start_row=0, row_count=2)
        assert isinstance(result, tuple) and len(result) == 5

    def test_first_element_is_png(self):
        draft = load_draft(MINIMAL_WIF)
        png, *_ = render_drawdown_tile(draft, start_row=0, row_count=2)
        assert png[:4] == b"\x89PNG"

    def test_second_element_is_total_rows(self):
        draft = load_draft(MINIMAL_WIF)
        _, total_rows, *_ = render_drawdown_tile(draft, start_row=0, row_count=2)
        assert total_rows == len(draft.weft)

    def test_third_element_is_actual_start_row(self):
        draft = load_draft(MINIMAL_WIF)
        _, _, actual_start, *_ = render_drawdown_tile(draft, start_row=1, row_count=2)
        assert actual_start == 1

    def test_fourth_element_is_actual_row_count(self):
        draft = load_draft(MINIMAL_WIF)
        _, _, _, actual_row_count, _ = render_drawdown_tile(draft, start_row=0, row_count=2)
        assert actual_row_count == 2

    def test_fifth_element_is_scale_used(self):
        draft = load_draft(MINIMAL_WIF)
        _, _, _, _, scale_used = render_drawdown_tile(draft, start_row=0, row_count=2, scale=10)
        assert scale_used == 10

    def test_tile_height_equals_row_count_times_scale(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, _, _, actual_row_count, scale_used = render_drawdown_tile(draft, start_row=0, row_count=2, scale=scale)
        img = Image.open(_io.BytesIO(png))
        assert img.height == actual_row_count * scale_used

    def test_tile_width_equals_warp_count_times_scale(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, _, _, _, scale_used = render_drawdown_tile(draft, start_row=0, row_count=2, scale=scale)
        img = Image.open(_io.BytesIO(png))
        assert img.width == len(draft.warp) * scale_used

    def test_row_count_clamped_at_draft_end(self):
        draft = load_draft(MINIMAL_WIF)
        _, total_rows, actual_start, actual_row_count, _ = render_drawdown_tile(draft, start_row=2, row_count=100)
        assert actual_start + actual_row_count <= total_rows

    def test_start_row_clamped_to_valid_range(self):
        draft = load_draft(MINIMAL_WIF)
        _, total_rows, actual_start, actual_row_count, _ = render_drawdown_tile(draft, start_row=999, row_count=2)
        assert actual_start <= total_rows - 1

    def test_default_row_count_renders_full_draft(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, total_rows, _, actual_row_count, scale_used = render_drawdown_tile(draft, start_row=0, scale=scale)
        img = Image.open(_io.BytesIO(png))
        assert actual_row_count == total_rows
        assert img.height == total_rows * scale_used

    def test_empty_draft_raises_value_error(self):
        draft = load_draft(MINIMAL_WIF)
        draft.warp = []
        with pytest.raises(ValueError, match="no drawdown data"):
            render_drawdown_tile(draft)

    def test_tile_from_middle_has_correct_dimensions(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, _, _, actual_row_count, scale_used = render_drawdown_tile(draft, start_row=1, row_count=2, scale=scale)
        img = Image.open(_io.BytesIO(png))
        assert img.height == actual_row_count * scale_used

    # --- column slicing ---

    def test_returns_seven_elements_when_col_params_given(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_drawdown_tile(draft, start_row=0, row_count=2, start_col=0, col_count=2)
        assert isinstance(result, tuple) and len(result) == 7

    def test_col_slice_width_equals_col_count_times_scale(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png, _, _, _, scale_used, _, actual_col_count = render_drawdown_tile(
            draft, start_row=0, row_count=2, scale=scale, start_col=0, col_count=2
        )
        img = Image.open(_io.BytesIO(png))
        assert img.width == actual_col_count * scale_used

    def test_col_slice_narrower_than_full_width(self):
        import io as _io

        from PIL import Image

        draft = load_draft(MINIMAL_WIF)
        scale = 10
        png_full, *_ = render_drawdown_tile(draft, start_row=0, row_count=2, scale=scale)
        png_col, *_ = render_drawdown_tile(draft, start_row=0, row_count=2, scale=scale, start_col=0, col_count=2)
        img_full = Image.open(_io.BytesIO(png_full))
        img_col = Image.open(_io.BytesIO(png_col))
        assert img_col.width < img_full.width
        assert img_col.width == 2 * scale

    def test_start_col_offsets_slice(self):
        draft = load_draft(MINIMAL_WIF)
        _, _, _, _, _, actual_start_col, _ = render_drawdown_tile(
            draft, start_row=0, row_count=2, start_col=1, col_count=2
        )
        assert actual_start_col == 1

    def test_col_count_clamped_at_draft_end(self):
        draft = load_draft(MINIMAL_WIF)
        warp_count = len(draft.warp)
        _, _, _, _, _, actual_start_col, actual_col_count = render_drawdown_tile(
            draft, start_row=0, row_count=2, start_col=2, col_count=100
        )
        assert actual_start_col + actual_col_count <= warp_count

    def test_start_col_clamped_to_valid_range(self):
        draft = load_draft(MINIMAL_WIF)
        warp_count = len(draft.warp)
        _, _, _, _, _, actual_start_col, _ = render_drawdown_tile(
            draft, start_row=0, row_count=2, start_col=999, col_count=2
        )
        assert actual_start_col <= warp_count - 1

    def test_no_col_params_returns_five_elements(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_drawdown_tile(draft, start_row=0, row_count=2)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# render_drawdown_preview
# ---------------------------------------------------------------------------


def _make_wide_wif(warp_threads: int) -> bytes:
    threading = "\n".join(f"{i + 1}={((i % 4) + 1)}" for i in range(warp_threads))
    treadling = "\n".join(f"{i + 1}={((i % 4) + 1)}" for i in range(warp_threads))
    return f"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

[WARP]
Threads={warp_threads}
Units=Inches
Color=1

[WEFT]
Threads={warp_threads}
Units=Inches
Color=2

[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=200,50,50
2=50,50,200

[THREADING]
{threading}

[TIEUP]
1=1
2=2
3=3
4=4

[TREADLING]
{treadling}
""".encode()


class TestRenderDrawdownPreview:
    def test_returns_tuple(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_drawdown_preview(draft)
        assert isinstance(result, tuple) and len(result) == 2

    def test_first_element_is_png(self):
        draft = load_draft(MINIMAL_WIF)
        png, _ = render_drawdown_preview(draft)
        assert png[:4] == b"\x89PNG"

    def test_second_element_is_scale(self):
        draft = load_draft(MINIMAL_WIF)
        _, scale = render_drawdown_preview(draft)
        assert isinstance(scale, int) and scale >= 1

    def test_wide_draft_scale_1_does_not_raise(self):
        """Regression: >200 warp threads forces scale<4; fill-marker patch must prevent crash."""
        draft = load_draft(_make_wide_wif(300))
        png, scale = render_drawdown_preview(draft, max_px=800)
        assert png[:4] == b"\x89PNG"
        assert scale < 4

    def test_very_wide_draft_scale_1(self):
        draft = load_draft(_make_wide_wif(900))
        png, scale = render_drawdown_preview(draft, max_px=800)
        assert png[:4] == b"\x89PNG"
        assert scale == 1

    def test_empty_draft_raises_value_error(self):
        draft = load_draft(MINIMAL_WIF)
        draft.warp = []
        with pytest.raises(ValueError, match="no drawdown data"):
            render_drawdown_preview(draft)


# ---------------------------------------------------------------------------
# Real-world liftplan WIF with stale Treadles= metadata (#266)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _SHADOW_FLOWERS_WIF.exists(),
    reason="Sample file not present in repo",
)
class TestLiftplanTreadles:
    def test_shadow_flowers_loads_without_assertion_error(self):
        wif_bytes = _SHADOW_FLOWERS_WIF.read_bytes()
        draft = load_draft(wif_bytes)
        assert len(draft.warp) > 0
        assert len(draft.weft) > 0

    def test_shadow_flowers_drawdown_renders(self):
        wif_bytes = _SHADOW_FLOWERS_WIF.read_bytes()
        draft = load_draft(wif_bytes)
        png, total_rows, scale_used = render_drawdown_only(draft)
        assert png[:4] == b"\x89PNG"
        assert total_rows == len(draft.weft)
        assert scale_used >= 1
