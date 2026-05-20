"""Independent tests for the Draft domain model.

Collected by CI via testpaths = tests in pytest.ini.
No WeftMark fixtures, database, or Celery stack required.
"""

import json

import pytest

from app.weaving import Color, Draft, WarpThread, WeftThread


class TestColor:
    def test_rgb_stored_as_tuple(self):
        c = Color([255, 0, 128])
        assert c.rgb == (255, 0, 128)

    def test_equality(self):
        assert Color((1, 2, 3)) == Color((1, 2, 3))
        assert Color((1, 2, 3)) != Color((1, 2, 4))

    def test_css(self):
        assert Color((255, 0, 0)).css == "rgb(255, 0, 0)"


class TestDraftCreation:
    def test_shaft_count(self):
        d = Draft(num_shafts=4, num_treadles=4)
        assert len(d.shafts) == 4

    def test_treadle_count(self):
        d = Draft(num_shafts=4, num_treadles=4)
        assert len(d.treadles) == 4

    def test_liftplan_when_no_treadles(self):
        d = Draft(num_shafts=4, num_treadles=0)
        assert d.liftplan is True

    def test_explicit_liftplan(self):
        d = Draft(num_shafts=4, num_treadles=0, liftplan=True)
        assert d.liftplan is True

    def test_empty_thread_lists(self):
        d = Draft(num_shafts=4, num_treadles=4)
        assert d.warp == []
        assert d.weft == []


def _make_plain_weave_4s() -> Draft:
    """4-shaft plain-weave treadle draft, 4 warp × 4 weft."""
    d = Draft(num_shafts=4, num_treadles=2)
    d.treadles[0].shafts = {d.shafts[0], d.shafts[2]}
    d.treadles[1].shafts = {d.shafts[1], d.shafts[3]}
    for ii in range(4):
        d.add_warp_thread(color=(0, 0, 0), shaft=ii % 4)
        d.add_weft_thread(color=(255, 255, 255), treadles=[ii % 2])
    return d


class TestThreadManipulation:
    def test_add_warp_thread(self):
        d = Draft(num_shafts=4, num_treadles=2)
        d.add_warp_thread(color=(0, 0, 255), shaft=0)
        assert len(d.warp) == 1
        assert d.warp[0].color.rgb == (0, 0, 255)

    def test_add_weft_thread_treadle(self):
        d = Draft(num_shafts=4, num_treadles=2)
        d.add_weft_thread(color=(255, 0, 0), treadles=[0])
        assert len(d.weft) == 1
        assert 0 in [d.treadles.index(t) for t in d.weft[0].treadles]

    def test_add_weft_thread_liftplan(self):
        d = Draft(num_shafts=4, num_treadles=0)
        d.add_weft_thread(color=(255, 0, 0), shafts=[0, 2])
        assert d.weft[0].shafts == {d.shafts[0], d.shafts[2]}

    def test_insert_warp_thread_at_index(self):
        d = Draft(num_shafts=4, num_treadles=2)
        d.add_warp_thread(color=(0, 0, 0), shaft=0)
        d.add_warp_thread(color=(255, 0, 0), shaft=1, index=0)
        assert d.warp[0].color.rgb == (255, 0, 0)

    def test_all_threads_attached(self):
        d = _make_plain_weave_4s()
        assert d.all_threads_attached() is True

    def test_all_threads_attached_missing_shaft(self):
        d = Draft(num_shafts=4, num_treadles=2)
        d.add_warp_thread(color=(0, 0, 0), shaft=None)
        assert d.all_threads_attached() is False


class TestDrawdown:
    def test_drawdown_returns_correct_shape(self):
        d = _make_plain_weave_4s()
        dd = d.compute_drawdown()
        assert len(dd) == 4
        assert len(dd[0]) == 4

    def test_drawdown_at_returns_thread(self):
        d = _make_plain_weave_4s()
        result = d.compute_drawdown_at((0, 0))
        assert isinstance(result, (WarpThread, WeftThread))

    def test_compute_floats_yields_tuples(self):
        d = _make_plain_weave_4s()
        floats = list(d.compute_floats())
        assert len(floats) > 0
        for item in floats:
            assert len(item) == 5

    def test_longest_floats_returns_ints(self):
        d = _make_plain_weave_4s()
        warp_max, weft_max = d.compute_longest_floats()
        assert isinstance(warp_max, int)
        assert isinstance(weft_max, int)


class TestJsonRoundtrip:
    def test_roundtrip_preserves_thread_counts(self):
        d = _make_plain_weave_4s()
        restored = Draft.from_json(d.to_json())
        assert len(restored.warp) == len(d.warp)
        assert len(restored.weft) == len(d.weft)

    def test_roundtrip_preserves_shaft_count(self):
        d = _make_plain_weave_4s()
        restored = Draft.from_json(d.to_json())
        assert len(restored.shafts) == len(d.shafts)

    def test_roundtrip_preserves_colors(self):
        d = _make_plain_weave_4s()
        restored = Draft.from_json(d.to_json())
        assert restored.warp[0].color.rgb == d.warp[0].color.rgb

    def test_to_json_is_valid_json(self):
        d = _make_plain_weave_4s()
        obj = json.loads(d.to_json())
        assert "warp" in obj
        assert "weft" in obj


class TestTransformations:
    def test_copy_is_independent(self):
        d = _make_plain_weave_4s()
        c = d.copy()
        c.warp[0].color = Color((1, 2, 3))
        assert d.warp[0].color.rgb != (1, 2, 3)

    def test_flip_weftwise_reverses_warp(self):
        d = _make_plain_weave_4s()
        original_last = d.warp[-1]
        d.flip_weftwise()
        assert d.warp[0] is original_last

    def test_flip_warpwise_reverses_weft(self):
        d = _make_plain_weave_4s()
        original_last = d.weft[-1]
        d.flip_warpwise()
        assert d.weft[0] is original_last

    def test_reduce_active_treadles(self):
        d = _make_plain_weave_4s()
        d.reduce_active_treadles()
        assert len(d.treadles) <= 2

    def test_not_implemented_stubs_raise(self):
        d = _make_plain_weave_4s()
        with pytest.raises(NotImplementedError):
            d.reduce_shafts()
        with pytest.raises(NotImplementedError):
            d.rotate()
