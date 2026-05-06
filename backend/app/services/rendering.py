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

from app.config import get_settings

DRAWDOWN_SCALE = 20


def load_draft(wif_bytes: bytes) -> Draft:
    """Parse WIF bytes and return a PyWeaving Draft."""
    with tempfile.NamedTemporaryFile(suffix=".wif", delete=False) as tmp:
        tmp.write(wif_bytes)
        tmp_path = tmp.name
    try:
        reader = WIFReader(tmp_path)
        return reader.read()
    finally:
        os.unlink(tmp_path)


def render_full_draft(draft: Draft, scale: int = 10) -> bytes:
    """Render threading + tie-up/liftplan + drawdown as a PNG."""
    renderer = ImageRenderer(draft, scale=scale)
    im = renderer.make_pil_image()
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


def render_full_draft_liftplan(draft: Draft, scale: int = 10) -> bytes:
    """Render the full draft using the liftplan view."""
    renderer = ImageRenderer(draft, liftplan=True, scale=scale)
    im = renderer.make_pil_image()
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


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
    full_im = renderer.make_pil_image()

    offsetx = margin
    offsety = margin + (6 + len(draft.shafts)) * scale
    cropped = full_im.crop((offsetx, offsety, offsetx + drawdown_w, offsety + drawdown_h))
    cropped = cropped.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue(), scale


def render_drawdown_only(draft: Draft, scale: int = DRAWDOWN_SCALE) -> tuple[bytes, int]:
    """Render just the drawdown strip, cropped from the full draft image.

    Returns (png_bytes, total_rows). Pick 1 is at the top of the image (y=0),
    last pick is at the bottom. Each row is ``scale`` pixels tall.
    """
    margin = 20
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    drawdown_w = warp_count * scale
    drawdown_h = weft_count * scale

    if drawdown_w <= 0 or drawdown_h <= 0:
        raise ValueError("Draft has no drawdown data to render")

    _s = get_settings()
    if drawdown_w > _s.render_max_width or drawdown_h > _s.render_max_height:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Draft dimensions ({drawdown_w}x{drawdown_h}px) exceed the rendering limit "
                f"({_s.render_max_width}x{_s.render_max_height}px)."
            ),
        )

    renderer = ImageRenderer(draft, scale=scale, margin_pixels=margin)
    full_im = renderer.make_pil_image()

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
    return out.getvalue(), weft_count
