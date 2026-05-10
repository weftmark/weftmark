"""
WIF rendering service using PyWeaving.

PyWeaving 0.0.7 calls draw.textsize() which was removed in Pillow 10.
We restore it before importing the renderer so PyWeaving works unmodified.
"""

from __future__ import annotations

import io
import os
import tempfile

from fastapi import HTTPException
from PIL import Image as PILImage
from PIL import ImageDraw as _ImageDraw

# Pillow ≥10 removed ImageDraw.textsize — patch it back for PyWeaving compatibility
if not hasattr(_ImageDraw.ImageDraw, "textsize"):

    def _textsize(self, text: str, font=None, *args, **kwargs):  # type: ignore[override]
        bbox = self.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    _ImageDraw.ImageDraw.textsize = _textsize  # type: ignore[attr-defined]

from pyweaving import Draft  # noqa: E402
from pyweaving.render import ImageRenderer  # noqa: E402
from pyweaving.wif import WIFReader  # noqa: E402


# PyWeaving's paint_fill_marker insets by 2px on each side; at scale < 4 this
# produces endx - 2 < startx + 2, causing Pillow to raise "x1 must be >= x0".
# Patch it to skip drawing when the cell is too small to fit the inset.
def _paint_fill_marker(self, draw, box):  # type: ignore[override]
    startx, starty, endx, endy = box
    x0, y0, x1, y1 = startx + 2, starty + 2, endx - 2, endy - 2
    if x0 < x1 and y0 < y1:
        draw.rectangle((x0, y0, x1, y1), fill=self.markers)


ImageRenderer.paint_fill_marker = _paint_fill_marker  # type: ignore[method-assign]

from opentelemetry import trace  # noqa: E402

from app.config import get_settings  # noqa: E402

tracer = trace.get_tracer(__name__)

DRAWDOWN_SCALE = 20


def load_draft(wif_bytes: bytes) -> Draft:
    """Parse WIF bytes and return a PyWeaving Draft."""
    from app.services.wif_modifier import zero_treadles_for_liftplan

    with tracer.start_as_current_span("wif.load_draft") as span:
        wif_bytes = zero_treadles_for_liftplan(wif_bytes)
        with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as tmp:
            tmp.write(wif_bytes)
            tmp_path = tmp.name
        try:
            reader = WIFReader(tmp_path)
            draft = reader.read()
            span.set_attribute("wif.warp_threads", len(draft.warp))
            span.set_attribute("wif.weft_threads", len(draft.weft))
            return draft
        finally:
            os.unlink(tmp_path)


def render_full_draft(draft: Draft, scale: int = 10) -> bytes:
    """Render threading + tie-up/liftplan + drawdown as a PNG."""
    renderer = ImageRenderer(draft, scale=scale)
    with tracer.start_as_current_span("render.full_draft") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", len(draft.warp))
        span.set_attribute("render.weft_threads", len(draft.weft))
        im = renderer.make_pil_image()
        span.set_attribute("render.width_px", im.width)
        span.set_attribute("render.height_px", im.height)
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def render_full_draft_liftplan(draft: Draft, scale: int = 10) -> bytes:
    """Render the full draft using the liftplan view."""
    renderer = ImageRenderer(draft, liftplan=True, scale=scale)
    with tracer.start_as_current_span("render.full_draft_liftplan") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", len(draft.warp))
        span.set_attribute("render.weft_threads", len(draft.weft))
        im = renderer.make_pil_image()
        span.set_attribute("render.width_px", im.width)
        span.set_attribute("render.height_px", im.height)
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def clip_draft_to_effective(draft: Draft, effective_shafts: int | None, effective_treadles: int | None) -> Draft:
    """Slice draft.shafts and draft.treadles to their effective counts.

    Modifies the draft in-place and returns it. Caller should pass a copy if
    the original object is reused.
    """
    if effective_shafts and effective_shafts < len(draft.shafts):
        draft.shafts = draft.shafts[:effective_shafts]
        for thread in draft.warp:
            thread.shaft = [s for s in thread.shaft if s in draft.shafts]
        if hasattr(draft, "tieup") and draft.tieup:
            draft.tieup = {k: v for k, v in draft.tieup.items() if k in draft.shafts}
    if effective_treadles and effective_treadles < len(draft.treadles):
        draft.treadles = draft.treadles[:effective_treadles]
        for thread in draft.weft:
            thread.treadles = [t for t in thread.treadles if t in draft.treadles]
        if hasattr(draft, "tieup") and draft.tieup:
            draft.tieup = {k: {t: v for t, v in row.items() if t in draft.treadles} for k, row in draft.tieup.items()}
    return draft


def render_drawdown_preview(draft: Draft, max_px: int = 800) -> tuple[bytes, int]:
    """Render a reduced-size drawdown for caching.

    Scales down so the image width fits within max_px. Returns (png_bytes, scale_used).
    Does not apply render_max_* limits — the reduced scale prevents oversized output.
    """
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    if warp_count <= 0 or weft_count <= 0:
        raise ValueError("Draft has no drawdown data to render")

    scale = max(1, min(DRAWDOWN_SCALE, max_px // warp_count))
    margin = 20
    drawdown_w = warp_count * scale
    drawdown_h = weft_count * scale

    renderer = ImageRenderer(draft, scale=scale, margin_pixels=margin)
    with tracer.start_as_current_span("render.drawdown_preview") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", warp_count)
        span.set_attribute("render.weft_threads", weft_count)
        full_im = renderer.make_pil_image()
        span.set_attribute("render.width_px", drawdown_w)
        span.set_attribute("render.height_px", drawdown_h)

    offsetx = margin
    offsety = margin + (6 + len(draft.shafts)) * scale
    cropped = full_im.crop((offsetx, offsety, offsetx + drawdown_w, offsety + drawdown_h))
    cropped = cropped.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue(), scale


def render_drawdown_tile(
    draft: Draft,
    start_row: int = 0,
    row_count: int | None = None,
    scale: int = DRAWDOWN_SCALE,
    effective_shafts: int | None = None,
    effective_treadles: int | None = None,
) -> tuple[bytes, int, int, int, int]:
    """Render a horizontal strip (tile) of the drawdown.

    ``start_row`` and ``row_count`` are in image-row terms:
    row 0 = top of the image = last pick (completed picks accumulate downward).

    Only the width cap from settings is applied — height is determined by ``row_count``.

    Returns (png_bytes, total_rows, actual_start_row, actual_row_count, scale_used).
    """
    if effective_shafts is not None or effective_treadles is not None:
        draft = clip_draft_to_effective(draft, effective_shafts, effective_treadles)

    margin = 20
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)

    if warp_count <= 0 or weft_count <= 0:
        raise ValueError("Draft has no drawdown data to render")

    _s = get_settings()
    max_scale = min(_s.render_max_width // warp_count, scale)
    if max_scale < 1:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Draft width ({warp_count} threads) exceeds the rendering limit "
                f"even at scale=1 ({_s.render_max_width}px max width)."
            ),
        )
    scale = max_scale

    actual_start = max(0, min(start_row, weft_count - 1))
    if row_count is None or row_count <= 0:
        row_count = weft_count
    actual_row_count = min(row_count, weft_count - actual_start)

    drawdown_w = warp_count * scale
    drawdown_h = weft_count * scale

    renderer = ImageRenderer(draft, scale=scale, margin_pixels=margin)
    with tracer.start_as_current_span("render.drawdown_tile") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", warp_count)
        span.set_attribute("render.weft_threads", weft_count)
        span.set_attribute("render.tile_start_row", actual_start)
        span.set_attribute("render.tile_row_count", actual_row_count)
        full_im = renderer.make_pil_image()
        span.set_attribute("render.width_px", warp_count * scale)
        span.set_attribute("render.height_px", actual_row_count * scale)

    offsetx = margin
    offsety = margin + (6 + len(draft.shafts)) * scale

    full_drawdown = full_im.crop((offsetx, offsety, offsetx + drawdown_w, offsety + drawdown_h))
    full_drawdown = full_drawdown.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)

    tile_top = actual_start * scale
    tile_bottom = tile_top + actual_row_count * scale
    tile = full_drawdown.crop((0, tile_top, drawdown_w, tile_bottom))

    out = io.BytesIO()
    tile.save(out, format="PNG")
    return out.getvalue(), weft_count, actual_start, actual_row_count, scale


def render_drawdown_only(
    draft: Draft,
    scale: int = DRAWDOWN_SCALE,
    effective_shafts: int | None = None,
    effective_treadles: int | None = None,
) -> tuple[bytes, int, int]:
    """Render just the drawdown strip, cropped from the full draft image.

    Returns (png_bytes, total_rows, scale_used). Pick 1 is at the top of the image (y=0),
    last pick is at the bottom. Each row is ``scale_used`` pixels tall.

    Scale is reduced automatically so the output fits within RENDER_MAX_WIDTH/HEIGHT.
    A 413 is raised only if scale=1 would still exceed the limits.
    """
    if effective_shafts is not None or effective_treadles is not None:
        draft = clip_draft_to_effective(draft, effective_shafts, effective_treadles)

    margin = 20
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)

    if warp_count <= 0 or weft_count <= 0:
        raise ValueError("Draft has no drawdown data to render")

    _s = get_settings()
    # Reduce scale to the largest integer that fits within the configured pixel limits.
    max_scale = min(
        _s.render_max_width // warp_count,
        _s.render_max_height // weft_count,
        scale,
    )
    if max_scale < 1:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Draft dimensions ({warp_count}×{weft_count} threads) exceed the rendering limit "
                f"even at scale=1 ({_s.render_max_width}×{_s.render_max_height}px max)."
            ),
        )
    scale = max_scale

    drawdown_w = warp_count * scale
    drawdown_h = weft_count * scale

    renderer = ImageRenderer(draft, scale=scale, margin_pixels=margin)
    with tracer.start_as_current_span("render.drawdown_only") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", warp_count)
        span.set_attribute("render.weft_threads", weft_count)
        full_im = renderer.make_pil_image()
        span.set_attribute("render.width_px", drawdown_w)
        span.set_attribute("render.height_px", drawdown_h)

    # The drawdown occupies the left portion of the image starting at x=0
    # (warp threads 0..N-1 at x = thread_idx * scale).
    # The treadle/shaft column is to the right at x = (1 + warp_count) * scale.
    offsetx = margin
    offsety = margin + (6 + len(draft.shafts)) * scale

    cropped = full_im.crop((offsetx, offsety, offsetx + drawdown_w, offsety + drawdown_h))
    # Flip vertically: pick 1 at bottom, last pick at top — completed picks accumulate below.
    cropped = cropped.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue(), weft_count, scale
