"""
Tests for app.services.rendering.

PyWeaving requires a real filesystem file, so load_draft uses a temp file
internally.  These tests verify the Pillow compat patch, basic parse
correctness, and that render output is valid PNG bytes.

A full PyWeaving-compatible WIF requires: [WIF] with Date, [CONTENTS],
[WEAVING] with Rising Shed, [WARP]/[WEFT] with Threads+Units+Color,
[COLOR TABLE], [THREADING], [TIEUP], [TREADLING].
"""

import sys

import pytest

from app.services.rendering import (
    DRAWDOWN_SCALE,
    load_draft,
    render_drawdown_only,
    render_full_draft,
    render_full_draft_liftplan,
)

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
# Pillow compatibility patch
# ---------------------------------------------------------------------------


class TestPillowPatch:
    def test_textsize_attribute_exists(self):
        """The Pillow >=10 compat patch must have added textsize back."""
        from PIL.ImageDraw import ImageDraw

        assert hasattr(ImageDraw, "textsize"), "Pillow compat patch missing — PyWeaving will fail to render"

    def test_textsize_callable(self):
        from PIL.ImageDraw import ImageDraw

        assert callable(getattr(ImageDraw, "textsize"))


# ---------------------------------------------------------------------------
# load_draft
# ---------------------------------------------------------------------------


class TestLoadDraft:
    def test_returns_draft_object(self):
        from pyweaving import Draft

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
        # scale=2 causes PyWeaving fill-marker math to go negative; min is ~4
        draft = load_draft(MINIMAL_WIF)
        small = render_full_draft(draft, scale=4)
        large = render_full_draft(draft, scale=10)
        assert len(large) > len(small)

    def test_eight_shaft_renders(self):
        draft = load_draft(EIGHT_SHAFT_WIF)
        result = render_full_draft(draft, scale=4)
        assert result[:4] == b"\x89PNG"

    def test_default_scale_produces_png(self):
        draft = load_draft(MINIMAL_WIF)
        result = render_full_draft(draft)
        assert result[:4] == b"\x89PNG"


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
        # scale=2 causes PyWeaving fill-marker math to go negative; min is ~4
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
