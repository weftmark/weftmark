"""Tests for app.services.wif_modifier."""

import pytest

from app.services.wif_modifier import set_weaving_int

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
