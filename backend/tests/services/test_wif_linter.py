"""
Tests for app.services.wif_linter.

Covers: feature detection, error/warning generation, metadata extraction,
encoding fallback, and malformed input handling.
"""

from app.services.wif_linter import LintResult, lint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_wif(
    *,
    wif_section: bool = True,
    weaving: bool = True,
    shafts: int = 8,
    treadles: int = 10,
    threading: bool = True,
    tieup: bool = True,
    treadling: bool = True,
    liftplan: bool = False,
    color_palette: bool = True,
    source_program: str | None = "TestLoom",
    source_version: str | None = "2.0",
    warp_threads: int | None = 120,
    weft_threads: int | None = 200,
) -> bytes:
    parts = []

    if wif_section:
        block = "[WIF]\nVersion=1.1"
        if source_program:
            block += f"\nSource Program={source_program}"
        if source_version:
            block += f"\nSource Version={source_version}"
        parts.append(block)

    if weaving:
        parts.append(f"[WEAVING]\nShafts={shafts}\nTreadles={treadles}")

    if warp_threads is not None:
        parts.append(f"[WARP]\nThreads={warp_threads}")

    if weft_threads is not None:
        parts.append(f"[WEFT]\nThreads={weft_threads}")

    if threading:
        parts.append("[THREADING]\n1=1\n2=2")

    if tieup:
        parts.append("[TIEUP]\n1=1\n2=2")

    if treadling:
        parts.append("[TREADLING]\n1=1\n2=2")

    if liftplan:
        parts.append("[LIFTPLAN]\n1=1,2\n2=3,4")

    if color_palette:
        parts.append("[COLOR PALETTE]\nRange=0,255\nForm=Decimal")

    return "\n\n".join(parts).encode()


FULL_WIF = make_wif()


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


def test_returns_lint_result():
    assert isinstance(lint(FULL_WIF), LintResult)


# ---------------------------------------------------------------------------
# Error-free path
# ---------------------------------------------------------------------------


class TestFullyFormedWIF:
    def setup_method(self):
        self.result = lint(FULL_WIF)

    def test_no_errors(self):
        assert self.result.errors == []

    def test_is_parseable(self):
        assert self.result.is_parseable is True

    def test_shaft_count(self):
        assert self.result.num_shafts == 8

    def test_treadle_count(self):
        assert self.result.num_treadles == 10

    def test_warp_threads(self):
        assert self.result.warp_threads == 120

    def test_weft_threads(self):
        assert self.result.weft_threads == 200

    def test_source_software(self):
        assert self.result.source_software == "TestLoom"

    def test_source_version(self):
        assert self.result.source_version == "2.0"

    def test_feature_flags(self):
        assert self.result.has_threading is True
        assert self.result.has_tieup is True
        assert self.result.has_treadling is True
        assert self.result.has_liftplan is False
        assert self.result.has_color_palette is True


# ---------------------------------------------------------------------------
# Required section errors
# ---------------------------------------------------------------------------


class TestMissingRequiredSections:
    def test_missing_wif_section_is_error(self):
        result = lint(make_wif(wif_section=False))
        assert any("[WIF]" in e for e in result.errors)

    def test_missing_weaving_section_is_error(self):
        result = lint(make_wif(weaving=False))
        assert any("[WEAVING]" in e for e in result.errors)

    def test_missing_weaving_clears_shaft_and_treadle_counts(self):
        result = lint(make_wif(weaving=False))
        assert result.num_shafts is None
        assert result.num_treadles is None


# ---------------------------------------------------------------------------
# Feature flag detection
# ---------------------------------------------------------------------------


class TestFeatureDetection:
    def test_no_threading(self):
        result = lint(make_wif(threading=False))
        assert result.has_threading is False

    def test_has_tieup(self):
        result = lint(make_wif(tieup=True))
        assert result.has_tieup is True

    def test_no_tieup(self):
        result = lint(make_wif(tieup=False))
        assert result.has_tieup is False

    def test_has_treadling(self):
        result = lint(make_wif(treadling=True))
        assert result.has_treadling is True

    def test_no_treadling(self):
        result = lint(make_wif(treadling=False))
        assert result.has_treadling is False

    def test_has_liftplan(self):
        result = lint(make_wif(liftplan=True))
        assert result.has_liftplan is True

    def test_no_liftplan(self):
        result = lint(make_wif(liftplan=False))
        assert result.has_liftplan is False

    def test_color_palette_via_color_table(self):
        content = b"""
[WIF]
Version=1.1

[WEAVING]
Shafts=4
Treadles=4

[COLOR TABLE]
1=255,0,0
""".strip()
        result = lint(content)
        assert result.has_color_palette is True

    def test_no_color_palette(self):
        result = lint(make_wif(color_palette=False))
        assert result.has_color_palette is False


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


class TestWarnings:
    def test_no_threading_warns(self):
        result = lint(make_wif(threading=False))
        assert any("THREADING" in w for w in result.warnings)

    def test_no_tieup_and_no_liftplan_warns(self):
        result = lint(make_wif(tieup=False, liftplan=False))
        assert any("TIEUP" in w or "LIFTPLAN" in w for w in result.warnings)

    def test_no_treadling_and_no_liftplan_warns(self):
        result = lint(make_wif(treadling=False, liftplan=False))
        assert any("TREADLING" in w or "LIFTPLAN" in w for w in result.warnings)

    def test_no_color_palette_warns(self):
        result = lint(make_wif(color_palette=False))
        assert any("COLOR" in w for w in result.warnings)

    def test_both_treadling_and_liftplan_warns(self):
        result = lint(make_wif(treadling=True, liftplan=True))
        assert any("TREADLING" in w and "LIFTPLAN" in w for w in result.warnings)

    def test_tieup_present_suppresses_tieup_liftplan_warning(self):
        result = lint(make_wif(tieup=True, liftplan=False))
        assert not any("TIEUP" in w and "LIFTPLAN" in w for w in result.warnings)

    def test_liftplan_present_suppresses_treadling_warning(self):
        result = lint(make_wif(treadling=False, liftplan=True))
        assert not any("step tracking unavailable" in w for w in result.warnings)

    def test_full_wif_has_minimal_warnings(self):
        """A fully-formed WIF should produce no warnings about missing sections."""
        result = lint(FULL_WIF)
        blocking = [w for w in result.warnings if "unavailable" in w]
        assert blocking == []


# ---------------------------------------------------------------------------
# Source software
# ---------------------------------------------------------------------------


class TestSourceSoftware:
    def test_source_program_extracted(self):
        result = lint(make_wif(source_program="WeavePoint"))
        assert result.source_software == "WeavePoint"

    def test_source_version_extracted(self):
        result = lint(make_wif(source_version="8.1"))
        assert result.source_version == "8.1"

    def test_missing_source_program_is_none(self):
        result = lint(make_wif(source_program=None))
        assert result.source_software is None

    def test_missing_source_version_is_none(self):
        result = lint(make_wif(source_version=None))
        assert result.source_version is None


# ---------------------------------------------------------------------------
# Thread counts
# ---------------------------------------------------------------------------


class TestThreadCounts:
    def test_warp_threads(self):
        result = lint(make_wif(warp_threads=240))
        assert result.warp_threads == 240

    def test_weft_threads(self):
        result = lint(make_wif(weft_threads=300))
        assert result.weft_threads == 300

    def test_missing_warp_section_leaves_none(self):
        result = lint(make_wif(warp_threads=None))
        assert result.warp_threads is None

    def test_missing_weft_section_leaves_none(self):
        result = lint(make_wif(weft_threads=None))
        assert result.weft_threads is None


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


class TestEncoding:
    def test_utf8(self):
        result = lint(FULL_WIF)
        assert result.is_parseable

    def test_latin1_fallback(self):
        content = make_wif(source_program="Caf\xe9Loom")
        result = lint(content)
        assert result.is_parseable

    def test_latin1_bytes_decoded(self):
        text = "[WIF]\nVersion=1.1\nSource Program=Caf\xe9Loom\n\n[WEAVING]\nShafts=4\nTreadles=4"
        content = text.encode("latin-1")
        result = lint(content)
        assert result.source_software == "CaféLoom"


# ---------------------------------------------------------------------------
# Malformed input
# ---------------------------------------------------------------------------


class TestMalformedInput:
    def test_empty_bytes(self):
        result = lint(b"")
        assert result.errors  # should have at least one error (missing [WIF])

    def test_not_ini_format(self):
        result = lint(b"this is not an ini file at all\x00\x01\x02")
        # Should not raise; may or may not be parseable but must return LintResult
        assert isinstance(result, LintResult)

    def test_is_parseable_false_on_cannot_parse_error(self):
        result = LintResult(errors=["Cannot parse file: something went wrong"])
        assert result.is_parseable is False

    def test_is_parseable_true_with_other_errors(self):
        result = LintResult(errors=["Missing [WIF] section"])
        assert result.is_parseable is True


# ---------------------------------------------------------------------------
# Malformed numeric field handling (exception paths in lint())
# ---------------------------------------------------------------------------


def _wif_with_weaving(shafts: str = "8", treadles: str = "10") -> bytes:
    return (
        f"[WIF]\nVersion=1.1\n"
        f"[WEAVING]\nShafts={shafts}\nTreadles={treadles}\n"
        f"[WARP]\nThreads=120\n"
        f"[WEFT]\nThreads=200\n"
        f"[THREADING]\n1=1\n[TIEUP]\n1=1\n[TREADLING]\n1=1\n"
    ).encode()


class TestMalformedNumericFields:
    def test_non_numeric_shafts_produces_warning(self):
        result = lint(_wif_with_weaving(shafts="not_a_number"))
        assert any("shaft" in w.lower() for w in result.warnings)

    def test_non_numeric_shafts_num_shafts_is_none(self):
        result = lint(_wif_with_weaving(shafts="not_a_number"))
        assert result.num_shafts is None

    def test_non_numeric_treadles_produces_warning(self):
        result = lint(_wif_with_weaving(treadles="not_a_number"))
        assert any("treadle" in w.lower() for w in result.warnings)

    def test_non_numeric_treadles_num_treadles_is_none(self):
        result = lint(_wif_with_weaving(treadles="not_a_number"))
        assert result.num_treadles is None

    def test_non_numeric_warp_threads_does_not_raise(self):
        content = (
            b"[WIF]\nVersion=1.1\n"
            b"[WEAVING]\nShafts=8\nTreadles=10\n"
            b"[WARP]\nThreads=not_a_number\n"
            b"[THREADING]\n1=1\n[TIEUP]\n1=1\n[TREADLING]\n1=1\n"
        )
        result = lint(content)
        assert isinstance(result, LintResult)
        assert result.warp_threads is None

    def test_non_numeric_weft_threads_does_not_raise(self):
        content = (
            b"[WIF]\nVersion=1.1\n"
            b"[WEAVING]\nShafts=8\nTreadles=10\n"
            b"[WEFT]\nThreads=not_a_number\n"
            b"[THREADING]\n1=1\n[TIEUP]\n1=1\n[TREADLING]\n1=1\n"
        )
        result = lint(content)
        assert isinstance(result, LintResult)
        assert result.weft_threads is None


# ---------------------------------------------------------------------------
# TestMaxIndexUsed — _max_index_used exception paths (lines 158-159, 169-170)
# ---------------------------------------------------------------------------


class TestMaxIndexUsed:
    def test_missing_section_returns_none(self):
        # Covers lines 158-159: config.items() raises NoSectionError → caught, return None
        from configparser import RawConfigParser

        from app.services.wif_linter import _max_index_used

        config = RawConfigParser()
        result = _max_index_used(config, "NONEXISTENT_SECTION")
        assert result is None

    def test_non_numeric_token_is_skipped(self):
        # Covers lines 169-170: non-numeric token in value → ValueError caught, continue
        content = (
            b"[WIF]\nVersion=1.1\n"
            b"[WEAVING]\nShafts=4\nTreadles=4\n"
            b"[THREADING]\n1=1\n[TIEUP]\n1=1\n"
            b"[TREADLING]\n1=abc\n2=2\n"
        )
        result = lint(content)
        assert result.effective_num_treadles == 2
