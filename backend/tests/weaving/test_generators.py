"""Tests for app.weaving.generators.twill and app.weaving.generators.tartan."""

from app.weaving import Draft
from app.weaving.generators.tartan import tartan
from app.weaving.generators.twill import twill

# ---------------------------------------------------------------------------
# TestTwill
# ---------------------------------------------------------------------------


class TestTwill:
    def test_returns_draft(self):
        draft = twill()
        assert isinstance(draft, Draft)

    def test_default_size_2_shafts(self):
        draft = twill(size=2)
        assert len(draft.shafts) == 4
        assert len(draft.treadles) == 4

    def test_size_3_shafts(self):
        draft = twill(size=3)
        assert len(draft.shafts) == 6
        assert len(draft.treadles) == 6

    def test_thread_count_size_2(self):
        draft = twill(size=2)
        assert len(draft.warp) == 16  # 8 * size
        assert len(draft.weft) == 16

    def test_thread_count_size_3(self):
        draft = twill(size=3)
        assert len(draft.warp) == 24  # 8 * size
        assert len(draft.weft) == 24

    def test_custom_warp_color(self):
        draft = twill(warp_color=(255, 0, 0))
        assert draft.warp[0].color.rgb == (255, 0, 0)

    def test_custom_weft_color(self):
        draft = twill(weft_color=(0, 255, 0))
        assert draft.weft[0].color.rgb == (0, 255, 0)

    def test_treadles_have_shafts_assigned(self):
        draft = twill(size=2)
        for treadle in draft.treadles:
            assert len(treadle.shafts) > 0


# ---------------------------------------------------------------------------
# TestTartan
# ---------------------------------------------------------------------------


class TestTartan:
    def test_returns_draft(self):
        draft = tartan("B24, K4, G36")
        assert isinstance(draft, Draft)

    def test_always_4_shafts(self):
        draft = tartan("B24, K4")
        assert len(draft.shafts) == 4
        assert len(draft.treadles) == 4

    def test_thread_count_single_color(self):
        # "B24" → colors list is [B24] + reversed([B24]) = [B24, B24] = 48 threads
        draft = tartan("B24")
        assert len(draft.warp) == 48
        assert len(draft.weft) == 48

    def test_thread_count_two_colors(self):
        # "B24, K4" → [B24, K4] + [K4, B24] → 2*(24+4) = 56
        draft = tartan("B24, K4")
        assert len(draft.warp) == 56

    def test_repeats_doubles_threads(self):
        single = tartan("B24", repeats=1)
        double = tartan("B24", repeats=2)
        assert len(double.warp) == 2 * len(single.warp)

    def test_treadles_assigned(self):
        draft = tartan("B24, K4")
        for treadle in draft.treadles:
            assert len(treadle.shafts) == 2

    def test_known_colors_parse_without_error(self):
        # Smoke test: all colour letters used in _COLOR_MAP
        draft = tartan("A2, G2, B2, K2, W2, Y2, R2, P2")
        assert len(draft.warp) > 0
