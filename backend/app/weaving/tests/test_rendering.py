"""Independent tests for the PNG rendering pipeline.

Run standalone: pytest backend/app/weaving/tests/test_rendering.py
No WeftMark fixtures, database, or Celery stack required.
Requires the font file at backend/app/weaving/data/Arial.ttf.
"""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.weaving import Draft
from app.weaving._render import _FONT_PATH, ImageRenderer

_FONT_AVAILABLE = Path(_FONT_PATH).exists()


def _skip_if_no_font():
    if not _FONT_AVAILABLE:
        pytest.skip("Font not available at app/weaving/data/Arial.ttf — skipping render tests")


def _make_twill_draft() -> Draft:
    d = Draft(num_shafts=4, num_treadles=4)
    for ii in range(4):
        for jj in range(2):
            d.treadles[ii].shafts.add(d.shafts[(ii + jj) % 4])
    for ii in range(16):
        d.add_warp_thread(color=(0, 0, 100), shaft=ii % 4)
        d.add_weft_thread(color=(255, 255, 255), treadles=[ii % 4])
    return d


def _make_liftplan_draft() -> Draft:
    d = Draft(num_shafts=4, num_treadles=0)
    for ii in range(8):
        d.add_warp_thread(color=(0, 0, 100), shaft=ii % 4)
        d.add_weft_thread(color=(255, 255, 255), shafts=[(ii % 4), (ii + 1) % 4])
    return d


class TestImageRendererBasic:
    def test_make_pil_image_returns_image(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        assert isinstance(im, Image.Image)

    def test_image_is_rgb(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        assert im.mode == "RGB"

    def test_image_has_positive_dimensions(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        assert im.width > 0
        assert im.height > 0

    def test_png_bytes_returned(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        out = io.BytesIO()
        im.save(out, format="PNG")
        assert out.getvalue()[:4] == b"\x89PNG"

    def test_small_scale_no_crash(self):
        """paint_fill_marker must not crash at scale=3 (2px inset would be invalid)."""
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, scale=3)
        im = renderer.make_pil_image()
        assert im.width > 0

    def test_liftplan_draft_renders(self):
        _skip_if_no_font()
        draft = _make_liftplan_draft()
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        assert isinstance(im, Image.Image)

    def test_liftplan_flag_overrides(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        renderer = ImageRenderer(draft, liftplan=True, scale=10)
        im = renderer.make_pil_image()
        assert isinstance(im, Image.Image)

    def test_margin_pixels_applied(self):
        _skip_if_no_font()
        draft = _make_twill_draft()
        no_margin = ImageRenderer(draft, scale=10, margin_pixels=0).make_pil_image()
        with_margin = ImageRenderer(draft, scale=10, margin_pixels=20).make_pil_image()
        assert with_margin.width == no_margin.width + 40
        assert with_margin.height == no_margin.height + 40

    def test_many_treadles_numbering_no_crash(self):
        """paint_tieup textbbox path is exercised when treadles >= 4."""
        _skip_if_no_font()
        draft = Draft(num_shafts=8, num_treadles=8)
        for ii in range(8):
            draft.treadles[ii].shafts.add(draft.shafts[ii])
        for ii in range(16):
            draft.add_warp_thread(color=(0, 0, 0), shaft=ii % 8)
            draft.add_weft_thread(color=(255, 255, 255), treadles=[ii % 8])
        renderer = ImageRenderer(draft, scale=10)
        im = renderer.make_pil_image()
        assert im.width > 0
