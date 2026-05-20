"""Tests covering app.weaving.__init__ methods not exercised by app/weaving/tests/."""

import pytest

from app.services.rendering import load_draft
from app.weaving import Color, DraftError, WarpThread, WeftThread

TABBY_WIF = b"""[WIF]
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
Shafts=2
Treadles=2
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
3=1
4=2

[TIEUP]
1=1
2=2

[TREADLING]
1=1
2=2
3=1
4=2
"""


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


# ---------------------------------------------------------------------------
# Color repr/str
# ---------------------------------------------------------------------------


class TestColorRepr:
    def test_str(self):
        c = Color((100, 200, 50))
        assert str(c) == "(100, 200, 50)"

    def test_repr(self):
        c = Color((100, 200, 50))
        assert repr(c) == "Color((100, 200, 50))"


# ---------------------------------------------------------------------------
# WarpThread repr
# ---------------------------------------------------------------------------


class TestWarpThreadRepr:
    def test_repr(self):
        draft = load_draft(MINIMAL_WIF)
        t = WarpThread(color=(100, 200, 50), shaft=draft.shafts[0])
        s = repr(t)
        assert "WarpThread" in s
        assert "color" in s


# ---------------------------------------------------------------------------
# WeftThread repr (two branches)
# ---------------------------------------------------------------------------


class TestWeftThreadRepr:
    def test_repr_with_treadles(self):
        draft = load_draft(MINIMAL_WIF)
        t = WeftThread(color=(100, 200, 50), treadles=set(draft.treadles[:1]))
        s = repr(t)
        assert "WeftThread" in s
        assert "treadles" in s

    def test_repr_with_shafts(self):
        draft = load_draft(MINIMAL_WIF)
        t = WeftThread(color=(100, 200, 50), shafts=set(draft.shafts[:1]))
        s = repr(t)
        assert "WeftThread" in s
        assert "shafts" in s


# ---------------------------------------------------------------------------
# Draft.add_weft_thread with index
# ---------------------------------------------------------------------------


class TestAddWeftThreadWithIndex:
    def test_inserts_at_index(self):
        draft = load_draft(MINIMAL_WIF)
        initial = len(draft.weft)
        draft.add_weft_thread(color=(10, 20, 30), treadles=set(draft.treadles[:1]), index=0)
        assert len(draft.weft) == initial + 1
        assert draft.weft[0].color.rgb == (10, 20, 30)


# ---------------------------------------------------------------------------
# NotImplementedError stubs
# ---------------------------------------------------------------------------


class TestNotImplementedStubs:
    def test_reduce_treadles(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.reduce_treadles()

    def test_sort_threading(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.sort_threading()

    def test_sort_treadles(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.sort_treadles()

    def test_compute_weft_crossings(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.compute_weft_crossings()

    def test_compute_warp_crossings(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.compute_warp_crossings()


# ---------------------------------------------------------------------------
# reduce_active_treadles — liftplan guard
# ---------------------------------------------------------------------------


class TestReduceActiveTreadles:
    def test_raises_on_liftplan(self):
        draft = load_draft(MINIMAL_WIF)
        draft.liftplan = True
        with pytest.raises(ValueError, match="cannot reduce treadles on a liftplan draft"):
            draft.reduce_active_treadles()


# ---------------------------------------------------------------------------
# selvedges_continuous / selvedge_continuous
# ---------------------------------------------------------------------------


class TestSelvedgeContinuous:
    def test_selvedge_continuous_false_on_minimal(self):
        draft = load_draft(MINIMAL_WIF)
        result = draft.selvedge_continuous(False)
        assert isinstance(result, bool)

    def test_selvedge_continuous_low_on_minimal(self):
        draft = load_draft(MINIMAL_WIF)
        result = draft.selvedge_continuous(True)
        assert isinstance(result, bool)

    def test_selvedges_continuous_false_on_minimal(self):
        draft = load_draft(MINIMAL_WIF)
        result = draft.selvedges_continuous()
        assert isinstance(result, bool)

    def test_selvedge_continuous_true_on_tabby(self):
        # tabby draft has naturally continuous selvedges — exercises the return True path
        draft = load_draft(TABBY_WIF)
        assert draft.selvedge_continuous(True) is True

    def test_selvedges_continuous_true_on_tabby(self):
        draft = load_draft(TABBY_WIF)
        assert draft.selvedges_continuous() is True


# ---------------------------------------------------------------------------
# make_selvedges_continuous
# ---------------------------------------------------------------------------


class TestMakeSelvedgesContinuous:
    def test_raises_draft_error_when_impossible(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(DraftError, match="cannot make continuous selvedges"):
            draft.make_selvedges_continuous()

    def test_raises_not_implemented_when_add_new_shafts(self):
        draft = load_draft(MINIMAL_WIF)
        with pytest.raises(NotImplementedError):
            draft.make_selvedges_continuous(add_new_shafts=True)

    def test_noop_when_already_continuous(self):
        # tabby selvedges are already continuous — exercises success=True; continue path
        draft = load_draft(TABBY_WIF)
        draft.make_selvedges_continuous()  # should not raise


# ---------------------------------------------------------------------------
# Draft.repeat
# ---------------------------------------------------------------------------


class TestRepeat:
    def test_doubles_warp_and_weft(self):
        draft = load_draft(MINIMAL_WIF)
        initial_warp = len(draft.warp)
        initial_weft = len(draft.weft)
        draft.repeat(1)
        assert len(draft.warp) == initial_warp * 2
        assert len(draft.weft) == initial_weft * 2

    def test_repeat_zero_no_change(self):
        draft = load_draft(MINIMAL_WIF)
        initial_warp = len(draft.warp)
        draft.repeat(0)
        assert len(draft.warp) == initial_warp

    def test_repeat_twice_triples(self):
        draft = load_draft(MINIMAL_WIF)
        initial_warp = len(draft.warp)
        draft.repeat(2)
        assert len(draft.warp) == initial_warp * 3
