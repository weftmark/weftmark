"""
Tests for custom OTel spans in wif_parser and rendering services (#458).

Uses an in-memory span exporter so tests run without a live OTel collector.
Each test asserts that the expected span name is emitted and that key
attributes are present with correct values.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.services import rendering, wif_parser

# ---------------------------------------------------------------------------
# Fixtures
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

TREADLING_AND_TIEUP = b"""[WIF]
Version=1.1

[TREADLING]
1=1
2=2
3=1,2

[TIEUP]
1=1,3
2=2,4
"""


@pytest.fixture
def span_exporter():
    """Install an in-memory TracerProvider for the duration of a test."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Patch the module-level tracers so spans land in our exporter.
    original_wif_tracer = wif_parser.tracer
    original_render_tracer = rendering.tracer
    wif_parser.tracer = provider.get_tracer("wif_parser")
    rendering.tracer = provider.get_tracer("rendering")

    yield exporter

    wif_parser.tracer = original_wif_tracer
    rendering.tracer = original_render_tracer
    exporter.shutdown()


def _span(exporter: InMemorySpanExporter, name: str):
    """Return the first finished span matching ``name``, or raise."""
    spans = [s for s in exporter.get_finished_spans() if s.name == name]
    assert spans, f"No span named {name!r}. Found: {[s.name for s in exporter.get_finished_spans()]}"
    return spans[0]


# ---------------------------------------------------------------------------
# wif_parser — parse_picks
# ---------------------------------------------------------------------------


class TestParsePicksSpan:
    def test_span_emitted(self, span_exporter):
        wif_parser.parse_picks(MINIMAL_WIF, "treadle")
        _span(span_exporter, "wif.parse_picks")

    def test_project_type_attribute(self, span_exporter):
        wif_parser.parse_picks(MINIMAL_WIF, "treadle")
        span = _span(span_exporter, "wif.parse_picks")
        assert span.attributes["wif.project_type"] == "treadle"

    def test_total_picks_attribute(self, span_exporter):
        wif_parser.parse_picks(MINIMAL_WIF, "treadle")
        span = _span(span_exporter, "wif.parse_picks")
        assert span.attributes["wif.total_picks"] == 4

    def test_lift_project_type_attribute(self, span_exporter):
        liftplan = b"[WIF]\nVersion=1.1\n\n[LIFTPLAN]\n1=1\n2=2\n3=3\n"
        wif_parser.parse_picks(liftplan, "lift")
        span = _span(span_exporter, "wif.parse_picks")
        assert span.attributes["wif.project_type"] == "lift"
        assert span.attributes["wif.total_picks"] == 3

    def test_span_status_ok_on_success(self, span_exporter):
        from opentelemetry.trace import StatusCode

        wif_parser.parse_picks(MINIMAL_WIF, "treadle")
        span = _span(span_exporter, "wif.parse_picks")
        assert span.status.status_code != StatusCode.ERROR


# ---------------------------------------------------------------------------
# wif_parser — compute_liftplan
# ---------------------------------------------------------------------------


class TestComputeLiftplanSpan:
    def test_span_emitted(self, span_exporter):
        wif_parser.compute_liftplan(TREADLING_AND_TIEUP)
        _span(span_exporter, "wif.compute_liftplan")

    def test_total_picks_attribute(self, span_exporter):
        wif_parser.compute_liftplan(TREADLING_AND_TIEUP)
        span = _span(span_exporter, "wif.compute_liftplan")
        assert span.attributes["wif.total_picks"] == 3


# ---------------------------------------------------------------------------
# rendering — load_draft
# ---------------------------------------------------------------------------


class TestLoadDraftSpan:
    def test_span_emitted(self, span_exporter):
        rendering.load_draft(MINIMAL_WIF)
        _span(span_exporter, "wif.load_draft")

    def test_warp_threads_attribute(self, span_exporter):
        rendering.load_draft(MINIMAL_WIF)
        span = _span(span_exporter, "wif.load_draft")
        assert span.attributes["wif.warp_threads"] == 4

    def test_weft_threads_attribute(self, span_exporter):
        rendering.load_draft(MINIMAL_WIF)
        span = _span(span_exporter, "wif.load_draft")
        assert span.attributes["wif.weft_threads"] == 4


# ---------------------------------------------------------------------------
# rendering — render_full_draft
# ---------------------------------------------------------------------------


class TestRenderFullDraftSpan:
    def test_span_emitted(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft(draft, scale=4)
        _span(span_exporter, "render.full_draft")

    def test_scale_attribute(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft(draft, scale=4)
        span = _span(span_exporter, "render.full_draft")
        assert span.attributes["render.scale"] == 4

    def test_thread_count_attributes(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft(draft, scale=4)
        span = _span(span_exporter, "render.full_draft")
        assert span.attributes["render.warp_threads"] == 4
        assert span.attributes["render.weft_threads"] == 4

    def test_output_dimensions_recorded(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft(draft, scale=4)
        span = _span(span_exporter, "render.full_draft")
        assert span.attributes["render.width_px"] > 0
        assert span.attributes["render.height_px"] > 0


# ---------------------------------------------------------------------------
# rendering — render_full_draft_liftplan
# ---------------------------------------------------------------------------


class TestRenderFullDraftLiftplanSpan:
    def test_span_emitted(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft_liftplan(draft, scale=4)
        _span(span_exporter, "render.full_draft_liftplan")

    def test_scale_attribute(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_full_draft_liftplan(draft, scale=4)
        span = _span(span_exporter, "render.full_draft_liftplan")
        assert span.attributes["render.scale"] == 4


# ---------------------------------------------------------------------------
# rendering — render_drawdown_preview
# ---------------------------------------------------------------------------


class TestRenderDrawdownPreviewSpan:
    def test_span_emitted(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_preview(draft)
        _span(span_exporter, "render.drawdown_preview")

    def test_scale_and_thread_attributes(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_preview(draft)
        span = _span(span_exporter, "render.drawdown_preview")
        assert span.attributes["render.warp_threads"] == 4
        assert span.attributes["render.weft_threads"] == 4
        assert span.attributes["render.scale"] >= 1


# ---------------------------------------------------------------------------
# rendering — render_drawdown_tile
# ---------------------------------------------------------------------------


class TestRenderDrawdownTileSpan:
    def test_span_emitted(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_tile(draft, start_row=0, row_count=2, scale=4)
        _span(span_exporter, "render.drawdown_tile")

    def test_tile_attributes(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_tile(draft, start_row=1, row_count=2, scale=4)
        span = _span(span_exporter, "render.drawdown_tile")
        assert span.attributes["render.scale"] == 4
        assert span.attributes["render.tile_start_row"] == 1
        assert span.attributes["render.tile_row_count"] == 2
        assert span.attributes["render.warp_threads"] == 4
        assert span.attributes["render.weft_threads"] == 4


# ---------------------------------------------------------------------------
# rendering — render_drawdown_only
# ---------------------------------------------------------------------------


class TestRenderDrawdownOnlySpan:
    def test_span_emitted(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_only(draft, scale=4)
        _span(span_exporter, "render.drawdown_only")

    def test_scale_and_dimension_attributes(self, span_exporter):
        draft = rendering.load_draft(MINIMAL_WIF)
        span_exporter.clear()
        rendering.render_drawdown_only(draft, scale=4)
        span = _span(span_exporter, "render.drawdown_only")
        assert span.attributes["render.scale"] == 4
        assert span.attributes["render.warp_threads"] == 4
        assert span.attributes["render.weft_threads"] == 4
        assert span.attributes["render.width_px"] == 4 * 4  # warp * scale
        assert span.attributes["render.height_px"] == 4 * 4  # weft * scale
