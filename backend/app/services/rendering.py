"""WIF rendering service backed by the vendored app.weaving engine."""

from __future__ import annotations

import io
import os
import tempfile

from fastapi import HTTPException
from opentelemetry import trace
from PIL import Image as PILImage

from app.config import get_settings
from app.weaving import Draft
from app.weaving._render import ImageRenderer, SVGRenderer
from app.weaving._render import drawdown_data as _drawdown_data
from app.weaving._render import drawdown_svg as _drawdown_svg
from app.weaving._wif import WIFReader

tracer = trace.get_tracer(__name__)

DRAWDOWN_SCALE = 20

# We generate images from WIF data we control — PIL's decompression bomb check
# is designed for untrusted external image files and does not apply here.
PILImage.MAX_IMAGE_PIXELS = None

_PREVIEW_MAX_PIXELS = 100_000_000  # 100 MP cap for synchronous preview renders


def safe_preview_scale(draft: Draft, desired_scale: int = 10) -> int:
    """Return the largest scale ≤ desired_scale that keeps the full image under _PREVIEW_MAX_PIXELS."""
    warp = len(draft.warp)
    weft = len(draft.weft)
    shaft_rows = 6 + len(draft.shafts)
    if warp <= 0 or weft <= 0:
        return desired_scale
    # full image approx: warp*s wide, (weft + shaft_rows)*s tall (ignoring small margins)
    max_scale = max(1, int((_PREVIEW_MAX_PIXELS / (warp * (weft + shaft_rows))) ** 0.5))
    return min(desired_scale, max_scale)


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
    scale = safe_preview_scale(draft, scale)
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


def render_full_draft_svg(draft: Draft, scale: int = 10) -> str:
    """Render the full draft (threading + tie-up/liftplan + drawdown) as an SVG string."""
    renderer = SVGRenderer(draft, scale=scale)
    with tracer.start_as_current_span("render.full_draft_svg") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", len(draft.warp))
        span.set_attribute("render.weft_threads", len(draft.weft))
        svg = renderer.render_to_string()
        span.set_attribute("render.svg_bytes", len(svg.encode()))
    return svg


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
    Uses render_drawdown_png so colors render correctly even at scale=1 — the
    ImageRenderer outline approach paints every pixel with the foreground gray at
    scale=1, obliterating thread colors.
    """
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    if warp_count <= 0 or weft_count <= 0:
        raise ValueError("Draft has no drawdown data to render")

    scale = max(1, min(DRAWDOWN_SCALE, max_px // warp_count))
    with tracer.start_as_current_span("render.drawdown_preview") as span:
        span.set_attribute("render.scale", scale)
        span.set_attribute("render.warp_threads", warp_count)
        span.set_attribute("render.weft_threads", weft_count)
        png_bytes = render_drawdown_png(draft, scale=scale)
        span.set_attribute("render.width_px", warp_count * scale)
        span.set_attribute("render.height_px", weft_count * scale)
    return png_bytes, scale


def render_drawdown_tile(
    draft: Draft,
    start_row: int = 0,
    row_count: int | None = None,
    scale: int = DRAWDOWN_SCALE,
    effective_shafts: int | None = None,
    effective_treadles: int | None = None,
    start_col: int | None = None,
    col_count: int | None = None,
) -> tuple[bytes, int, int, int, int] | tuple[bytes, int, int, int, int, int, int]:
    """Render a tile of the drawdown.

    When ``start_col`` / ``col_count`` are omitted the full warp width is
    returned and the result is a 5-tuple
    ``(png_bytes, total_rows, actual_start_row, actual_row_count, scale_used)``.

    When ``start_col`` / ``col_count`` are given a column-sliced tile is returned
    and the result is a 7-tuple extending the above with
    ``(actual_start_col, actual_col_count)``.

    ``start_row`` / ``start_col`` are 0-based; row 0 = top of the drawdown image
    (= last pick, since completed picks accumulate downward).
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

    if start_col is None:
        tile = full_drawdown.crop((0, tile_top, drawdown_w, tile_bottom))
        out = io.BytesIO()
        tile.save(out, format="PNG")
        return out.getvalue(), weft_count, actual_start, actual_row_count, scale

    actual_start_col = max(0, min(start_col, warp_count - 1))
    if col_count is None or col_count <= 0:
        col_count = warp_count
    actual_col_count = min(col_count, warp_count - actual_start_col)

    tile_left = actual_start_col * scale
    tile_right = tile_left + actual_col_count * scale
    tile = full_drawdown.crop((tile_left, tile_top, tile_right, tile_bottom))
    out = io.BytesIO()
    tile.save(out, format="PNG")
    return out.getvalue(), weft_count, actual_start, actual_row_count, scale, actual_start_col, actual_col_count


def render_drawdown_data(draft: Draft, cell_px: int = 20) -> dict:
    """Return float geometry as a dict for JSON delivery to the canvas renderer."""
    with tracer.start_as_current_span("render.drawdown_data") as span:
        span.set_attribute("render.cell_px", cell_px)
        span.set_attribute("render.warp_threads", len(draft.warp))
        span.set_attribute("render.weft_threads", len(draft.weft))
        data = _drawdown_data(draft, cell_px=cell_px)
        span.set_attribute("render.float_count", len(data["floats"]))
    return data


def render_drawdown_svg(draft: Draft, cell_px: int = 20) -> str:
    """Render the drawdown grid as a symbol-deduped SVG string.

    Suitable for project step-tracking: load once, highlight current pick via
    CSS/DOM on the client — zero server round-trips per step advance or reverse.
    """
    with tracer.start_as_current_span("render.drawdown_svg") as span:
        span.set_attribute("render.cell_px", cell_px)
        span.set_attribute("render.warp_threads", len(draft.warp))
        span.set_attribute("render.weft_threads", len(draft.weft))
        svg = _drawdown_svg(draft, cell_px=cell_px)
        span.set_attribute("render.svg_bytes", len(svg.encode()))
    return svg


def apply_color_replacements(draft: Draft, color_map: dict[str, str]) -> None:
    """Replace thread colors in-place based on a hex→hex mapping.

    ``color_map`` maps source hex strings (e.g. ``"#ff0000"``) to replacement
    hex strings.  Comparison is case-insensitive.  Threads whose color does not
    appear in the map are left unchanged.
    """
    if not color_map:
        return
    normalized: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for src, dst in color_map.items():
        src_rgb = tuple(int(src.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        dst_rgb = tuple(int(dst.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        normalized[src_rgb] = dst_rgb  # type: ignore[assignment]

    from app.weaving import Color

    for thread in (*draft.warp, *draft.weft):
        if thread.color is not None and thread.color.rgb in normalized:
            thread.color = Color(normalized[thread.color.rgb])


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


def render_drawdown_png(draft: Draft, scale: int = 1) -> bytes:
    """Render just the drawdown grid as a PNG, without cropping from a full draft image.

    Uses the same warp-up/weft-background logic as the SVG renderer so colors are
    consistent. Orientation: last pick at y=0 (top), first pick at bottom — matching
    the SVG drawdown and the step-tracking tile renderer.

    Returns raw PNG bytes.
    """
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    scale = max(1, scale)
    w = warp_count * scale
    h = weft_count * scale

    img = PILImage.new("RGB", (w, h), (255, 255, 255))
    pixels = img.load()

    warp_rgbs = [t.color.rgb if t.color else (0, 0, 0) for t in draft.warp]

    for weft_idx, weft_thread in enumerate(draft.weft):
        # Flip vertically: weft index 0 is the first pick (bottom); render it last row.
        svg_row = weft_count - 1 - weft_idx
        y0 = svg_row * scale

        weft_rgb = weft_thread.color.rgb if weft_thread.color else (255, 255, 255)

        # Fill entire row with weft color.
        for dy in range(scale):
            for x in range(w):
                pixels[x, y0 + dy] = weft_rgb  # type: ignore[index]

        # Paint warp-up threads on top.
        connected = weft_thread.connected_shafts
        warp_up = (x for x, wt in enumerate(draft.warp) if (wt.shaft not in connected) ^ draft.rising_shed)
        for x in warp_up:
            rgb = warp_rgbs[x]
            x0 = x * scale
            for dy in range(scale):
                for dx in range(scale):
                    pixels[x0 + dx, y0 + dy] = rgb  # type: ignore[index]

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
