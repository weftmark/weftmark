"""
WIF rendering service using PyWeaving.

PyWeaving 0.0.7 calls draw.textsize() which was removed in Pillow 10.
We restore it before importing the renderer so PyWeaving works unmodified.
"""

from __future__ import annotations

import io
import tempfile
import os
from PIL import ImageDraw as _ImageDraw

# Pillow ≥10 removed ImageDraw.textsize — patch it back for PyWeaving compatibility
if not hasattr(_ImageDraw.ImageDraw, "textsize"):
    def _textsize(self, text: str, font=None, *args, **kwargs):  # type: ignore[override]
        bbox = self.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    _ImageDraw.ImageDraw.textsize = _textsize  # type: ignore[attr-defined]

from pyweaving.wif import WIFReader  # noqa: E402
from pyweaving.render import ImageRenderer  # noqa: E402
from pyweaving import Draft  # noqa: E402


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
