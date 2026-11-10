"""Tests for app.services.fingerprints — structural draft fingerprinting (#983)."""

from app.services.fingerprints import (
    compute_drawdown_fingerprint,
    compute_threading_fingerprint,
    compute_tieup_fingerprint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wif(threading: str = "", tieup: str = "", treadling: str = "", shafts: int = 4, treadles: int = 4) -> bytes:
    text = f"""[WIF]
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
Treadles={treadles}
Rising Shed=true

[WARP]
Threads=2
Units=Inches
Color=1

[WEFT]
Threads=2
Units=Inches
Color=2

[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=200,50,50
2=50,50,200

{threading}

{tieup}

{treadling}
""".strip()
    return text.encode("utf-8")


_THREADING_4 = "[THREADING]\n1=1\n2=2\n3=3\n4=4"
_TIEUP_4 = "[TIEUP]\n1=1\n2=2\n3=3\n4=4"
_TREADLING_4 = "[TREADLING]\n1=1\n2=2\n3=3\n4=4"


# ---------------------------------------------------------------------------
# TestThreadingFingerprint
# ---------------------------------------------------------------------------


class TestThreadingFingerprint:
    def test_deterministic(self):
        wif_bytes = _wif(threading=_THREADING_4)
        first = compute_threading_fingerprint(wif_bytes)
        second = compute_threading_fingerprint(wif_bytes)
        assert first == second

    def test_returns_none_when_section_absent(self):
        wif_bytes = _wif()
        assert compute_threading_fingerprint(wif_bytes) is None

    def test_returns_none_when_all_ends_unassigned(self):
        wif_bytes = _wif(threading="[THREADING]\n1=\n2=\n3=\n4=")
        assert compute_threading_fingerprint(wif_bytes) is None

    def test_different_threading_produces_different_hash(self):
        a = compute_threading_fingerprint(_wif(threading=_THREADING_4))
        b = compute_threading_fingerprint(_wif(threading="[THREADING]\n1=2\n2=1\n3=4\n4=3"))
        assert a != b

    def test_shaft_order_within_an_end_does_not_change_hash(self):
        a = compute_threading_fingerprint(_wif(threading="[THREADING]\n1=1,2\n2=3"))
        b = compute_threading_fingerprint(_wif(threading="[THREADING]\n1=2,1\n2=3"))
        assert a == b
        assert a is not None


# ---------------------------------------------------------------------------
# TestTieupFingerprint
# ---------------------------------------------------------------------------


class TestTieupFingerprint:
    def test_deterministic(self):
        wif_bytes = _wif(tieup=_TIEUP_4)
        first = compute_tieup_fingerprint(wif_bytes)
        second = compute_tieup_fingerprint(wif_bytes)
        assert first == second

    def test_returns_none_when_section_absent(self):
        wif_bytes = _wif()
        assert compute_tieup_fingerprint(wif_bytes) is None

    def test_returns_none_when_all_treadles_unassigned(self):
        # parse_tieup raises ValueError only when the section is fully absent or
        # entirely empty — a section with keys present but every value blank
        # (e.g. Treadles count higher than any populated key) reaches the
        # degenerate-empty guard in compute_tieup_fingerprint instead.
        wif_bytes = _wif(tieup="[TIEUP]\n1=", treadles=2)
        assert compute_tieup_fingerprint(wif_bytes) is None

    def test_different_tieup_produces_different_hash(self):
        a = compute_tieup_fingerprint(_wif(tieup=_TIEUP_4))
        b = compute_tieup_fingerprint(_wif(tieup="[TIEUP]\n1=2\n2=1\n3=4\n4=3"))
        assert a != b

    def test_shaft_order_within_a_treadle_does_not_change_hash(self):
        a = compute_tieup_fingerprint(_wif(tieup="[TIEUP]\n1=1,2\n2=3"))
        b = compute_tieup_fingerprint(_wif(tieup="[TIEUP]\n1=2,1\n2=3"))
        assert a == b
        assert a is not None


# ---------------------------------------------------------------------------
# TestDrawdownFingerprint
# ---------------------------------------------------------------------------


class TestDrawdownFingerprint:
    def test_deterministic(self):
        wif_bytes = _wif(threading=_THREADING_4, tieup=_TIEUP_4, treadling=_TREADLING_4)
        first = compute_drawdown_fingerprint(wif_bytes)
        second = compute_drawdown_fingerprint(wif_bytes)
        assert first == second

    def test_returns_none_when_zero_warp_threads(self):
        wif_bytes = _wif(threading="[THREADING]", tieup=_TIEUP_4, treadling=_TREADLING_4).replace(
            b"Threads=2\nUnits=Inches\nColor=1", b"Threads=0\nUnits=Inches\nColor=1"
        )
        assert compute_drawdown_fingerprint(wif_bytes) is None

    def test_permuted_tieup_with_compensating_treadling_matches(self):
        """Two WIFs with a permuted [TIEUP] + compensating [TREADLING] produce the
        same physical fabric (same drawdown_fingerprint) despite different
        tieup_fingerprint — this is the entire reason drawdown_fingerprint exists
        as a third, independent hash rather than being derived from the other two."""
        threading = "[THREADING]\n1=1\n2=2"

        # Version A: treadle1->shaft1, treadle2->shaft2; pick1 uses treadle1, pick2 uses treadle2
        wif_a = _wif(
            threading=threading,
            tieup="[TIEUP]\n1=1\n2=2",
            treadling="[TREADLING]\n1=1\n2=2",
            shafts=2,
            treadles=2,
        )
        # Version B: treadle1->shaft2, treadle2->shaft1 (permuted); treadling swapped to compensate
        wif_b = _wif(
            threading=threading,
            tieup="[TIEUP]\n1=2\n2=1",
            treadling="[TREADLING]\n1=2\n2=1",
            shafts=2,
            treadles=2,
        )

        fp_a = compute_drawdown_fingerprint(wif_a)
        fp_b = compute_drawdown_fingerprint(wif_b)
        assert fp_a is not None
        assert fp_a == fp_b

        tieup_a = compute_tieup_fingerprint(wif_a)
        tieup_b = compute_tieup_fingerprint(wif_b)
        assert tieup_a != tieup_b

    def test_different_drawdown_produces_different_hash(self):
        a = compute_drawdown_fingerprint(_wif(threading=_THREADING_4, tieup=_TIEUP_4, treadling=_TREADLING_4))
        b = compute_drawdown_fingerprint(
            _wif(threading=_THREADING_4, tieup=_TIEUP_4, treadling="[TREADLING]\n1=2\n2=1\n3=4\n4=3")
        )
        assert a != b
