"""Independent tests for WIF I/O.

Collected by CI via testpaths = tests in pytest.ini.
No WeftMark fixtures, database, or Celery stack required.
"""

import os
import tempfile
from configparser import RawConfigParser
from pathlib import Path

from app.weaving import Draft
from app.weaving._wif import WIFReader, WIFWriter

_FIXTURES = Path(__file__).parent / "fixtures"


class TestWIFReader:
    def test_reads_plain_weave_fixture(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert isinstance(draft, Draft)

    def test_correct_shaft_count(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert len(draft.shafts) == 4

    def test_correct_treadle_count(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert len(draft.treadles) == 2

    def test_correct_warp_thread_count(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert len(draft.warp) == 4

    def test_correct_weft_thread_count(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert len(draft.weft) == 4

    def test_warp_thread_has_shaft(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert draft.all_threads_attached()

    def test_weft_thread_has_treadles(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert all(len(t.treadles) > 0 for t in draft.weft)

    def test_colors_parsed(self):
        path = str(_FIXTURES / "plain_weave_4s.wif")
        draft = WIFReader(path).read()
        assert draft.warp[0].color is not None
        assert draft.weft[0].color is not None


class TestWIFWriter:
    def _round_trip(self, draft: Draft) -> Draft:
        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as f:
            path = f.name
        try:
            WIFWriter(draft).write(path)
            return WIFReader(path).read()
        finally:
            os.unlink(path)

    def _make_draft(self) -> Draft:
        d = Draft(num_shafts=4, num_treadles=2)
        d.treadles[0].shafts = {d.shafts[0], d.shafts[2]}
        d.treadles[1].shafts = {d.shafts[1], d.shafts[3]}
        for ii in range(4):
            d.add_warp_thread(color=(0, 0, 0), shaft=ii % 4)
            d.add_weft_thread(color=(255, 255, 255), treadles=[ii % 2])
        return d

    def test_roundtrip_shaft_count(self):
        d = self._make_draft()
        restored = self._round_trip(d)
        assert len(restored.shafts) == len(d.shafts)

    def test_roundtrip_warp_thread_count(self):
        d = self._make_draft()
        restored = self._round_trip(d)
        assert len(restored.warp) == len(d.warp)

    def test_roundtrip_weft_thread_count(self):
        d = self._make_draft()
        restored = self._round_trip(d)
        assert len(restored.weft) == len(d.weft)

    def test_roundtrip_all_threads_attached(self):
        d = self._make_draft()
        restored = self._round_trip(d)
        assert restored.all_threads_attached()


def _write_temp_wif(content: str) -> str:
    """Write WIF content to a temp file and return its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".wif", delete=False, encoding="utf-8") as f:
        f.write(content)
        return f.name


# ---------------------------------------------------------------------------
# TestWIFReaderEdgeCases — cover paths not exercised by the plain_weave fixture
# ---------------------------------------------------------------------------


_WIF_NO_PER_THREAD_COLORS = """\
[WIF]
Version=1.1
Date=Jan 01, 2024

[CONTENTS]
COLOR TABLE=1
WARP=1
WEFT=1
THREADING=1
TREADLING=1
TIEUP=1
WEAVING=1

[COLOR TABLE]
1=0,0,0
2=255,255,255

[WEAVING]
Rising Shed=true
Shafts=4
Treadles=2

[WARP]
Threads=2
Units=Inches
Color=1

[WEFT]
Threads=2
Units=Inches
Color=2

[THREADING]
1=1
2=2

[TREADLING]
1=1
2=2

[TIEUP]
1=1
2=2
"""

_WIF_LIFTPLAN = """\
[WIF]
Version=1.1
Date=Jan 01, 2024

[CONTENTS]
COLOR TABLE=1
WARP=1
WEFT=1
THREADING=1
LIFTPLAN=1
WEAVING=1

[COLOR TABLE]
1=0,0,0
2=255,255,255

[WEAVING]
Rising Shed=true
Shafts=4
Treadles=0

[WARP]
Threads=2
Units=Inches
Color=1

[WEFT]
Threads=2
Units=Inches
Color=2

[THREADING]
1=1
2=2

[LIFTPLAN]
1=1,3
2=2,4
"""

_WIF_NO_COLOR_TABLE = """\
[WIF]
Version=1.1
Date=Jan 01, 2024

[CONTENTS]
WARP=1
WEFT=1
THREADING=1
TREADLING=1
TIEUP=1
WEAVING=1

[WEAVING]
Rising Shed=true
Shafts=2
Treadles=2

[WARP]
Threads=2
Units=Inches
Color=1

[WEFT]
Threads=2
Units=Inches
Color=2

[THREADING]
1=1
2=2

[TREADLING]
1=1
2=2

[TIEUP]
1=1
2=2
"""

_WIF_NO_COLOR_PALETTE = """\
[WIF]
Version=1.1
Date=Jan 01, 2024

[CONTENTS]
COLOR TABLE=1
WARP=1
WEFT=1
THREADING=1
TREADLING=1
TIEUP=1
WEAVING=1

[COLOR TABLE]
1=0,0,0
2=255,255,255

[WEAVING]
Rising Shed=true
Shafts=2
Treadles=2

[WARP]
Threads=2
Units=Inches
Color=1

[WEFT]
Threads=2
Units=Inches
Color=2

[THREADING]
1=1
2=2

[TREADLING]
1=1
2=2

[TIEUP]
1=1
2=2
"""


class TestWIFReaderEdgeCases:
    def test_reads_without_per_thread_colors(self):
        path = _write_temp_wif(_WIF_NO_PER_THREAD_COLORS)
        try:
            draft = WIFReader(path).read()
            assert len(draft.warp) == 2
            assert draft.warp[0].color is not None
        finally:
            os.unlink(path)

    def test_reads_liftplan_draft(self):
        path = _write_temp_wif(_WIF_LIFTPLAN)
        try:
            draft = WIFReader(path).read()
            assert draft.liftplan is True
            assert len(draft.weft) == 2
            assert len(draft.weft[0].shafts) > 0
        finally:
            os.unlink(path)

    def test_reads_without_color_table_section(self):
        # Regression: WIF with no COLOR TABLE caused TypeError: 'NoneType' object
        # is not subscriptable in put_warp / put_weft (Sentry WEFTMARK-BACKEND-FASTAPI-1)
        path = _write_temp_wif(_WIF_NO_COLOR_TABLE)
        try:
            draft = WIFReader(path).read()
            assert len(draft.warp) == 2
            assert len(draft.weft) == 2
        finally:
            os.unlink(path)

    def test_black_fallback_color_without_color_table(self):
        path = _write_temp_wif(_WIF_NO_COLOR_TABLE)
        try:
            draft = WIFReader(path).read()
            assert draft.warp[0].color is not None
            assert draft.weft[0].color is not None
        finally:
            os.unlink(path)

    def test_reads_without_color_palette_section(self):
        path = _write_temp_wif(_WIF_NO_COLOR_PALETTE)
        try:
            draft = WIFReader(path).read()
            assert len(draft.warp) == 2
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# TestWIFWriterEdgeCases — cover write_liftplan, notes, and liftplan roundtrip
# ---------------------------------------------------------------------------


class TestWIFWriterEdgeCases:
    def _make_liftplan_draft(self) -> Draft:
        d = Draft(num_shafts=4, num_treadles=0)
        for ii in range(4):
            d.add_warp_thread(color=(0, 0, 0), shaft=ii % 4)
            d.add_weft_thread(color=(255, 255, 255), shafts=[ii % 4])
        return d

    def test_writes_liftplan_draft(self):
        d = self._make_liftplan_draft()
        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as f:
            path = f.name
        try:
            WIFWriter(d).write(path)
            config = RawConfigParser()
            config.read(path)
            assert config.has_section("LIFTPLAN")
        finally:
            os.unlink(path)

    def test_liftplan_roundtrip_weft_count(self):
        d = self._make_liftplan_draft()
        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as f:
            path = f.name
        try:
            WIFWriter(d).write(path)
            restored = WIFReader(path).read()
            assert len(restored.weft) == len(d.weft)
        finally:
            os.unlink(path)

    def test_writes_notes_when_set(self):
        d = Draft(num_shafts=4, num_treadles=2)
        d.notes = "Line one\nLine two"
        d.treadles[0].shafts = {d.shafts[0]}
        d.treadles[1].shafts = {d.shafts[1]}
        for ii in range(2):
            d.add_warp_thread(color=(0, 0, 0), shaft=ii % 2)
            d.add_weft_thread(color=(255, 255, 255), treadles=[ii % 2])

        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as f:
            path = f.name
        try:
            WIFWriter(d).write(path)
            config = RawConfigParser()
            config.read(path)
            assert config.has_section("NOTES")
        finally:
            os.unlink(path)

    def test_explicit_liftplan_flag_uses_liftplan_section(self):
        """write(liftplan=True) on a treadle draft still emits LIFTPLAN."""
        d = Draft(num_shafts=4, num_treadles=2)
        d.treadles[0].shafts = {d.shafts[0], d.shafts[2]}
        d.treadles[1].shafts = {d.shafts[1], d.shafts[3]}
        for ii in range(4):
            d.add_warp_thread(color=(0, 0, 0), shaft=ii % 4)
            d.add_weft_thread(color=(255, 255, 255), treadles=[ii % 2])

        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as f:
            path = f.name
        try:
            WIFWriter(d).write(path, liftplan=True)
            config = RawConfigParser()
            config.read(path)
            assert config.has_section("LIFTPLAN")
            assert not config.has_section("TREADLING")
        finally:
            os.unlink(path)
