"""Tests for app.services.wif_modifier."""

import pytest

from app.services.wif_modifier import set_weaving_int, zero_treadles_for_liftplan

_MINIMAL_WIF = b"""[WIF]
Version=1.1
Date=April 20 1997
Developers=wif@mhsoft.com
Source Program=WeftMark
Source Version=1.0

[CONTENTS]
THREADING=false
TIEUP=false
TREADLING=false

[WEAVING]
Shafts=4
Treadles=4
"""


class TestSetWeavingInt:
    def test_replaces_existing_key(self):
        result = set_weaving_int(_MINIMAL_WIF, "Shafts", 8)
        assert b"Shafts=8" in result
        assert b"Shafts=4" not in result

    def test_other_keys_unchanged(self):
        result = set_weaving_int(_MINIMAL_WIF, "Shafts", 8)
        assert b"Treadles=4" in result

    def test_appends_missing_key(self):
        result = set_weaving_int(_MINIMAL_WIF, "Rising", 1)
        assert b"Rising=1" in result
        assert b"Shafts=4" in result

    def test_key_match_is_case_insensitive(self):
        result = set_weaving_int(_MINIMAL_WIF, "shafts", 16)
        assert b"shafts=16" in result

    def test_returns_bytes(self):
        result = set_weaving_int(_MINIMAL_WIF, "Shafts", 8)
        assert isinstance(result, bytes)

    def test_utf8_encoding_preserved(self):
        result = set_weaving_int(_MINIMAL_WIF, "Shafts", 8)
        result.decode("utf-8")

    def test_latin1_input_accepted(self):
        # Inject a non-UTF-8 byte (0xe9 = é in latin-1) into the WIF comment so
        # the UTF-8 decode fails and the latin-1 fallback path is exercised.
        wif_with_latin1 = _MINIMAL_WIF.replace(b"WeftMark", b"Weft\xe9Mark")
        result = set_weaving_int(wif_with_latin1, "Shafts", 8)
        assert b"Shafts=8" in result

    def test_raises_when_no_weaving_section(self):
        bad_wif = b"[WIF]\nVersion=1.1\n[THREADING]\nsome=data\n"
        with pytest.raises(ValueError, match=r"no \[WEAVING\] section"):
            set_weaving_int(bad_wif, "Shafts", 8)

    def test_append_places_key_after_section_header(self):
        result = set_weaving_int(_MINIMAL_WIF, "Units", 2)
        text = result.decode("utf-8")
        weaving_idx = text.index("[WEAVING]")
        units_idx = text.index("Units=2")
        assert units_idx > weaving_idx


_LIFTPLAN_WIF_WITH_TREADLES = b"""[WIF]
Version=1.1
Date=June 2025
Source Program=TempoWeave Designer

[WEAVING]
Shafts=8
Treadles=8
Rising Shed=true

[LIFTPLAN]
1=1,2,3
2=4,5,6
"""

_LIFTPLAN_WIF_NO_TREADLES = b"""[WIF]
Version=1.1
Date=June 2025
Source Program=TempoWeave Designer

[WEAVING]
Shafts=8
Treadles=0
Rising Shed=true

[LIFTPLAN]
1=1,2,3
"""

_TREADLE_WIF = b"""[WIF]
Version=1.1
Date=June 2025
Source Program=TestSuite

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

[TREADLING]
1=1
2=2
"""


class TestZeroTreadlesForLiftplan:
    def test_zeros_treadles_when_liftplan_without_treadling(self):
        result = zero_treadles_for_liftplan(_LIFTPLAN_WIF_WITH_TREADLES)
        assert b"Treadles=0" in result
        assert b"Treadles=8" not in result

    def test_noop_when_treadles_already_zero(self):
        result = zero_treadles_for_liftplan(_LIFTPLAN_WIF_NO_TREADLES)
        assert b"Treadles=0" in result

    def test_noop_when_no_liftplan_section(self):
        result = zero_treadles_for_liftplan(_TREADLE_WIF)
        assert result == _TREADLE_WIF

    def test_noop_when_both_liftplan_and_treadling_present(self):
        both = _LIFTPLAN_WIF_WITH_TREADLES + b"\n[TREADLING]\n1=1\n"
        result = zero_treadles_for_liftplan(both)
        assert result == both

    def test_returns_bytes(self):
        result = zero_treadles_for_liftplan(_LIFTPLAN_WIF_WITH_TREADLES)
        assert isinstance(result, bytes)

    def test_liftplan_section_preserved(self):
        result = zero_treadles_for_liftplan(_LIFTPLAN_WIF_WITH_TREADLES)
        assert b"[LIFTPLAN]" in result

    def test_latin1_input_accepted(self):
        # Inject a non-UTF-8 byte (0xe9 = é in latin-1) so the UTF-8 decode
        # fails and the latin-1 fallback path (lines 65-66) is exercised.
        wif_with_latin1 = _LIFTPLAN_WIF_WITH_TREADLES.replace(b"TempoWeave", b"Tempo\xe9Weave")
        result = zero_treadles_for_liftplan(wif_with_latin1)
        assert b"Treadles=0" in result
