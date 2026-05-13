# Copyright 2014-2015 Scott Torborg (storborg@gmail.com) — MIT License
# Vendored and modernised by WeftMark. See UPSTREAM_LICENSE for full text.
#
# Changes from upstream:
#   - Dropped Python 2/3 compat shims (from __future__ import)
#   - Fixed paint_fill_marker: skip draw when cell is too small for the 2px inset
#   - Fixed paint_tieup: replaced removed Pillow textsize() with textbbox()
#   - Font path resolved relative to this package's data/ directory

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_DATA_DIR = Path(__file__).parent / "data"
_FONT_PATH = str(_DATA_DIR / "Arial.ttf")


class ImageRenderer:
    def __init__(
        self,
        draft,
        liftplan=None,
        margin_pixels: int = 20,
        scale: int = 10,
        foreground=(127, 127, 127),
        background=(255, 255, 255),
        markers=(0, 0, 0),
        numbering=(200, 0, 0),
    ):
        self.draft = draft
        self.liftplan = liftplan
        self.margin_pixels = margin_pixels
        self.pixels_per_square = scale
        self.background = background
        self.foreground = foreground
        self.markers = markers
        self.numbering = numbering
        self.font_size = int(round(scale * 1.2))
        self.font = ImageFont.truetype(_FONT_PATH, self.font_size)

    def pad_image(self, im: Image.Image) -> Image.Image:
        w, h = im.size
        new = Image.new("RGB", (w + self.margin_pixels * 2, h + self.margin_pixels * 2), self.background)
        new.paste(im, (self.margin_pixels, self.margin_pixels))
        return new

    def make_pil_image(self) -> Image.Image:
        width_squares = len(self.draft.warp) + 6
        if self.liftplan or self.draft.liftplan:
            width_squares += len(self.draft.shafts)
        else:
            width_squares += len(self.draft.treadles)
        height_squares = len(self.draft.weft) + 6 + len(self.draft.shafts)

        # +1 prevents content overflow at the canvas edge
        width = width_squares * self.pixels_per_square + 1
        height = height_squares * self.pixels_per_square + 1

        im = Image.new("RGB", (width, height), self.background)
        draw = ImageDraw.Draw(im)

        self.paint_warp(draw)
        self.paint_threading(draw)
        self.paint_weft(draw)
        if self.liftplan or self.draft.liftplan:
            self.paint_liftplan(draw)
        else:
            self.paint_tieup(draw)
            self.paint_treadling(draw)
        self.paint_drawdown(draw)
        self.paint_start_indicator(draw)
        del draw

        return self.pad_image(im)

    def paint_start_indicator(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        endy = (len(self.draft.shafts) + 6) * pps - 1
        starty = endy - pps // 2
        if self.draft.start_at_lowest_thread:
            endx = len(self.draft.warp) * pps
            startx = endx - pps
        else:
            startx, endx = 0, pps
        draw.polygon(
            [(startx, starty), (endx, starty), (startx + pps // 2, endy)],
            fill=self.markers,
        )

    def paint_warp(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        for ii, thread in enumerate(self.draft.warp):
            startx = pps * ii
            draw.rectangle((startx, 0, startx + pps, pps), outline=self.foreground, fill=thread.color.rgb)

    def paint_fill_marker(self, draw: ImageDraw.ImageDraw, box: tuple) -> None:
        startx, starty, endx, endy = box
        x0, y0, x1, y1 = startx + 2, starty + 2, endx - 2, endy - 2
        if x0 < x1 and y0 < y1:
            draw.rectangle((x0, y0, x1, y1), fill=self.markers)

    def paint_threading(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        num_threads = len(self.draft.warp)
        num_shafts = len(self.draft.shafts)

        for ii, thread in enumerate(self.draft.warp):
            startx = (num_threads - ii - 1) * pps
            endx = startx + pps

            for jj, shaft in enumerate(self.draft.shafts):
                starty = (4 + num_shafts - jj) * pps
                endy = starty + pps
                draw.rectangle((startx, starty, endx, endy), outline=self.foreground)
                if shaft == thread.shaft:
                    self.paint_fill_marker(draw, (startx, starty, endx, endy))

            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                tick_x = (num_threads - ii - 1) * pps
                tick_ys, tick_ye = 3 * pps, 5 * pps - 1
                draw.line((tick_x, tick_ys, tick_x, tick_ye), fill=self.numbering)
                draw.text((tick_x + 2, tick_ys + 2), str(thread_no), font=self.font, fill=self.numbering)

    def paint_weft(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        offsety = (6 + len(self.draft.shafts)) * pps
        startx_sq = len(self.draft.warp) + 5
        if self.liftplan or self.draft.liftplan:
            startx_sq += len(self.draft.shafts)
        else:
            startx_sq += len(self.draft.treadles)
        startx = startx_sq * pps

        for ii, thread in enumerate(self.draft.weft):
            starty = ii * pps + offsety
            draw.rectangle((startx, starty, startx + pps, starty + pps), outline=self.foreground, fill=thread.color.rgb)

    def paint_liftplan(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        num_threads = len(self.draft.weft)
        offsetx = (1 + len(self.draft.warp)) * pps
        offsety = (6 + len(self.draft.shafts)) * pps

        for ii, thread in enumerate(self.draft.weft):
            starty = ii * pps + offsety
            endy = starty + pps

            for jj, shaft in enumerate(self.draft.shafts):
                startx = jj * pps + offsetx
                endx = startx + pps
                draw.rectangle((startx, starty, endx, endy), outline=self.foreground)
                if shaft in thread.connected_shafts:
                    self.paint_fill_marker(draw, (startx, starty, endx, endy))

            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                line_startx = offsetx + len(self.draft.shafts) * pps
                draw.line((line_startx, endy, line_startx + 2 * pps, endy), fill=self.numbering)
                draw.text(
                    (line_startx + 2, endy - 2 - self.font_size),
                    str(thread_no),
                    font=self.font,
                    fill=self.numbering,
                )

    def paint_tieup(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        offsetx = (1 + len(self.draft.warp)) * pps
        offsety = 5 * pps
        num_treadles = len(self.draft.treadles)
        num_shafts = len(self.draft.shafts)

        for ii, treadle in enumerate(self.draft.treadles):
            startx = ii * pps + offsetx
            endx = startx + pps
            treadle_no = ii + 1

            for jj, shaft in enumerate(self.draft.shafts):
                starty = (num_shafts - jj - 1) * pps + offsety
                endy = starty + pps
                draw.rectangle((startx, starty, endx, endy), outline=self.foreground)
                if shaft in treadle.shafts:
                    self.paint_fill_marker(draw, (startx, starty, endx, endy))

                if treadle_no == num_treadles:
                    shaft_no = jj + 1
                    if shaft_no != 0 and shaft_no % 4 == 0:
                        lx = endx
                        draw.line((lx, starty, lx + 2 * pps, starty), fill=self.numbering)
                        draw.text((lx + 2, starty + 2), str(shaft_no), font=self.font, fill=self.numbering)

            if treadle_no != 0 and treadle_no % 4 == 0:
                tick_x = treadle_no * pps + offsetx
                tick_ys, tick_ye = 3 * pps, 5 * pps - 1
                draw.line((tick_x, tick_ys, tick_x, tick_ye), fill=self.numbering)
                # textbbox replaces removed textsize (Pillow ≥10)
                bbox = draw.textbbox((0, 0), str(treadle_no), font=self.font)
                textw = bbox[2] - bbox[0]
                draw.text((tick_x - textw - 2, tick_ys + 2), str(treadle_no), font=self.font, fill=self.numbering)

    def paint_treadling(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        num_threads = len(self.draft.weft)
        offsetx = (1 + len(self.draft.warp)) * pps
        offsety = (6 + len(self.draft.shafts)) * pps

        for ii, thread in enumerate(self.draft.weft):
            starty = ii * pps + offsety
            endy = starty + pps

            for jj, treadle in enumerate(self.draft.treadles):
                startx = jj * pps + offsetx
                endx = startx + pps
                draw.rectangle((startx, starty, endx, endy), outline=self.foreground)
                if treadle in thread.treadles:
                    self.paint_fill_marker(draw, (startx, starty, endx, endy))

            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                line_startx = offsetx + len(self.draft.treadles) * pps
                draw.line((line_startx, endy, line_startx + 2 * pps, endy), fill=self.numbering)
                draw.text(
                    (line_startx + 2, endy - 2 - self.font_size),
                    str(thread_no),
                    font=self.font,
                    fill=self.numbering,
                )

    def paint_drawdown(self, draw: ImageDraw.ImageDraw) -> None:
        pps = self.pixels_per_square
        offsety = (6 + len(self.draft.shafts)) * pps
        for start, end, visible, length, thread in self.draft.compute_floats():
            if visible:
                startx = start[0] * pps
                starty = start[1] * pps + offsety
                endx = (end[0] + 1) * pps
                endy = (end[1] + 1) * pps + offsety
                draw.rectangle((startx, starty, endx, endy), outline=self.foreground, fill=thread.color.rgb)

    def show(self) -> None:
        self.make_pil_image().show()

    def save(self, filename: str) -> None:
        self.make_pil_image().save(filename)


# ---------------------------------------------------------------------------
# SVG renderer
# ---------------------------------------------------------------------------

_SVG_PREAMBLE = '<?xml version="1.0" encoding="utf-8" standalone="no"?>'
_SVG_HEADER = (
    '<svg width="{width}" height="{height}" '
    'viewBox="0 0 {width} {height}" '
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:xlink="http://www.w3.org/1999/xlink">'
)


class _TagGenerator:
    def __getattr__(self, name):
        def tag(*children, **attrs):
            inner = "".join(children)
            if attrs:
                attr_str = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
                return f"<{name} {attr_str}>{inner}</{name}>"
            return f"<{name}>{inner}</{name}>"

        return tag


_SVG = _TagGenerator()


class SVGRenderer:
    def __init__(
        self,
        draft,
        liftplan=None,
        scale: int = 10,
        foreground: str = "#7f7f7f",
        background: str = "#ffffff",
        markers: str = "#000000",
        numbering: str = "#c80000",
    ):
        self.draft = draft
        self.liftplan = liftplan
        self.scale = scale
        self.background = background
        self.foreground = foreground
        self.markers = markers
        self.numbering = numbering
        self.font_family = "Arial, sans-serif"
        self.font_size = 12

    def make_svg_doc(self) -> str:
        s = self.scale
        width_sq = len(self.draft.warp) + 6
        if self.liftplan or self.draft.liftplan:
            width_sq += len(self.draft.shafts)
        else:
            width_sq += len(self.draft.treadles)
        height_sq = len(self.draft.weft) + 6 + len(self.draft.shafts)

        doc = [_SVG_HEADER.format(width=width_sq * s, height=height_sq * s)]
        doc.append(_SVG.title(self.draft.title))
        self.paint_warp(doc)
        self.paint_threading(doc)
        self.paint_weft(doc)
        if self.liftplan or self.draft.liftplan:
            self.paint_liftplan(doc)
        else:
            self.paint_tieup(doc)
            self.paint_treadling(doc)
        self.paint_drawdown(doc)
        doc.append("</svg>")
        return "\n".join(doc)

    def paint_warp(self, doc) -> None:
        s = self.scale
        grp = []
        for ii, thread in enumerate(self.draft.warp):
            grp.append(
                _SVG.rect(
                    x=s * ii,
                    y=0,
                    width=s,
                    height=s,
                    style=f"stroke:{self.foreground}; fill:{thread.color.css}",
                )
            )
        doc.append(_SVG.g(*grp))

    def paint_weft(self, doc) -> None:
        s = self.scale
        offsety = (6 + len(self.draft.shafts)) * s
        startx_sq = len(self.draft.warp) + 5
        if self.liftplan or self.draft.liftplan:
            startx_sq += len(self.draft.shafts)
        else:
            startx_sq += len(self.draft.treadles)
        startx = startx_sq * s

        grp = []
        for ii, thread in enumerate(self.draft.weft):
            grp.append(
                _SVG.rect(
                    x=startx,
                    y=ii * s + offsety,
                    width=s,
                    height=s,
                    style=f"stroke:{self.foreground}; fill:{thread.color.css}",
                )
            )
        doc.append(_SVG.g(*grp))

    def paint_fill_marker(self, doc, box) -> None:
        startx, starty, endx, endy = box
        doc.append(
            _SVG.rect(
                x=startx + 2,
                y=starty + 2,
                width=self.scale - 4,
                height=self.scale - 4,
                style=f"fill:{self.markers}",
            )
        )

    def paint_threading(self, doc) -> None:
        s = self.scale
        num_threads = len(self.draft.warp)
        num_shafts = len(self.draft.shafts)
        grp = []
        for ii, thread in enumerate(self.draft.warp):
            startx = (num_threads - ii - 1) * s
            endx = startx + s
            for jj, shaft in enumerate(self.draft.shafts):
                starty = (4 + num_shafts - jj) * s
                endy = starty + s
                grp.append(
                    _SVG.rect(
                        x=startx,
                        y=starty,
                        width=s,
                        height=s,
                        style=f"stroke:{self.foreground}; fill:{self.background}",
                    )
                )
                if shaft == thread.shaft:
                    self.paint_fill_marker(grp, (startx, starty, endx, endy))
            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                tx = (num_threads - ii - 1) * s
                grp.append(_SVG.line(x1=tx, y1=3 * s, x2=tx, y2=5 * s - 1, style=f"stroke:{self.numbering}"))
                grp.append(
                    _SVG.text(
                        str(thread_no),
                        x=tx + 3,
                        y=3 * s + self.font_size,
                        style=f"font-family:{self.font_family}; font-size:{self.font_size}; fill:{self.numbering}",
                    )
                )
        doc.append(_SVG.g(*grp))

    def paint_liftplan(self, doc) -> None:
        s = self.scale
        num_threads = len(self.draft.weft)
        offsetx = (1 + len(self.draft.warp)) * s
        offsety = (6 + len(self.draft.shafts)) * s
        grp = []
        for ii, thread in enumerate(self.draft.weft):
            starty = ii * s + offsety
            endy = starty + s
            for jj, shaft in enumerate(self.draft.shafts):
                startx = jj * s + offsetx
                endx = startx + s
                grp.append(
                    _SVG.rect(
                        x=startx,
                        y=starty,
                        width=s,
                        height=s,
                        style=f"stroke:{self.foreground}; fill:{self.background}",
                    )
                )
                if shaft in thread.connected_shafts:
                    self.paint_fill_marker(grp, (startx, starty, endx, endy))
            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                lx = offsetx + len(self.draft.shafts) * s
                grp.append(_SVG.line(x1=lx, y1=endy, x2=lx + 2 * s, y2=endy, style=f"stroke:{self.numbering}"))
                grp.append(
                    _SVG.text(
                        str(thread_no),
                        x=lx + 3,
                        y=endy - 4,
                        style=f"font-family:{self.font_family}; font-size:{self.font_size}; fill:{self.numbering}",
                    )
                )
        doc.append(_SVG.g(*grp))

    def paint_tieup(self, doc) -> None:
        s = self.scale
        offsetx = (1 + len(self.draft.warp)) * s
        offsety = 5 * s
        num_treadles = len(self.draft.treadles)
        num_shafts = len(self.draft.shafts)
        grp = []
        for ii, treadle in enumerate(self.draft.treadles):
            startx = ii * s + offsetx
            endx = startx + s
            treadle_no = ii + 1
            for jj, shaft in enumerate(self.draft.shafts):
                starty = (num_shafts - jj - 1) * s + offsety
                endy = starty + s
                grp.append(
                    _SVG.rect(
                        x=startx,
                        y=starty,
                        width=s,
                        height=s,
                        style=f"stroke:{self.foreground}; fill:{self.background}",
                    )
                )
                if shaft in treadle.shafts:
                    self.paint_fill_marker(grp, (startx, starty, endx, endy))
                if treadle_no == num_treadles:
                    shaft_no = jj + 1
                    if shaft_no != 0 and shaft_no % 4 == 0:
                        lx = endx
                        grp.append(
                            _SVG.line(x1=lx, y1=starty, x2=lx + 2 * s, y2=starty, style=f"stroke:{self.numbering}")
                        )
                        grp.append(
                            _SVG.text(
                                str(shaft_no),
                                x=lx + 3,
                                y=starty + 2 + self.font_size,
                                style=(
                                    f"font-family:{self.font_family}; font-size:{self.font_size}; fill:{self.numbering}"
                                ),
                            )
                        )
            if treadle_no != 0 and treadle_no % 4 == 0:
                tx = treadle_no * s + offsetx
                grp.append(_SVG.line(x1=tx, y1=3 * s, x2=tx, y2=5 * s - 1, style=f"stroke:{self.numbering}"))
                grp.append(
                    _SVG.text(
                        str(treadle_no),
                        x=tx - 3,
                        y=3 * s + self.font_size,
                        text_anchor="end",
                        style=f"font-family:{self.font_family}; font-size:{self.font_size}; fill:{self.numbering}",
                    )
                )
        doc.append(_SVG.g(*grp))

    def paint_treadling(self, doc) -> None:
        s = self.scale
        num_threads = len(self.draft.weft)
        offsetx = (1 + len(self.draft.warp)) * s
        offsety = (6 + len(self.draft.shafts)) * s
        grp = []
        for ii, thread in enumerate(self.draft.weft):
            starty = ii * s + offsety
            endy = starty + s
            for jj, treadle in enumerate(self.draft.treadles):
                startx = jj * s + offsetx
                endx = startx + s
                grp.append(
                    _SVG.rect(
                        x=startx,
                        y=starty,
                        width=s,
                        height=s,
                        style=f"stroke:{self.foreground}; fill:{self.background}",
                    )
                )
                if treadle in thread.treadles:
                    self.paint_fill_marker(grp, (startx, starty, endx, endy))
            thread_no = ii + 1
            if thread_no != num_threads and thread_no != 0 and thread_no % 4 == 0:
                lx = offsetx + len(self.draft.treadles) * s
                grp.append(_SVG.line(x1=lx, y1=endy, x2=lx + 2 * s, y2=endy, style=f"stroke:{self.numbering}"))
                grp.append(
                    _SVG.text(
                        str(thread_no),
                        x=lx + 3,
                        y=endy - 4,
                        style=f"font-family:{self.font_family}; font-size:{self.font_size}; fill:{self.numbering}",
                    )
                )
        doc.append(_SVG.g(*grp))

    def paint_drawdown(self, doc) -> None:
        s = self.scale
        offsety = (6 + len(self.draft.shafts)) * s
        grp = []
        for start, end, visible, length, thread in self.draft.compute_floats():
            if visible:
                startx = start[0] * s
                starty = start[1] * s + offsety
                w = (end[0] - start[0] + 1) * s
                h = (end[1] - start[1] + 1) * s
                grp.append(
                    _SVG.rect(
                        x=startx,
                        y=starty,
                        width=w,
                        height=h,
                        style=f"stroke:{self.foreground}; fill:{thread.color.css}",
                    )
                )
        doc.append(_SVG.g(*grp))

    def render_to_string(self) -> str:
        return self.make_svg_doc()

    def save(self, filename: str) -> None:
        s = _SVG_PREAMBLE + "\n" + self.make_svg_doc()
        with open(filename, "w") as f:
            f.write(s)


# ---------------------------------------------------------------------------
# Symbol-deduped drawdown SVG (project step tracking)
# ---------------------------------------------------------------------------


def drawdown_svg(draft, cell_px: int = 20) -> str:
    """Render the drawdown as a symbol-deduped SVG string with float-boundary borders.

    DOM layout: O(weft) background rects + O(unique lift patterns) <symbol> defs
    + O(weft) <use> refs.  Borders are drawn as a single <path> whose sub-paths
    are one outline rect per visible float — so no internal cell borders appear
    within multi-cell floats.

    Orientation: last pick at y=0 (top), first pick at bottom.

    Returns an SVG string without an XML declaration — suitable for
    dangerouslySetInnerHTML injection.
    """
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    total_w = warp_count * cell_px
    total_h = weft_count * cell_px

    warp_colors = [t.color.css for t in draft.warp]

    symbol_map: dict[tuple[int, ...], int] = {}
    symbol_defs: list[str] = []
    row_data: list[tuple[int, str]] = []

    for weft_thread in draft.weft:
        connected = weft_thread.connected_shafts
        warp_up = tuple(x for x, wt in enumerate(draft.warp) if (wt.shaft not in connected) ^ draft.rising_shed)
        if warp_up not in symbol_map:
            sid = len(symbol_map)
            symbol_map[warp_up] = sid
            rects = "".join(
                f'<rect x="{x * cell_px}" y="0" width="{cell_px}" height="{cell_px}" fill="{warp_colors[x]}"/>'
                for x in warp_up
            )
            symbol_defs.append(f'<symbol id="s{sid}" width="{total_w}" height="{cell_px}">{rects}</symbol>')
        weft_css = weft_thread.color.css if weft_thread.color else "#ffffff"
        row_data.append((symbol_map[warp_up], weft_css))

    rows: list[str] = []
    for weft_idx, (sid, weft_css) in enumerate(row_data):
        svg_row = weft_count - 1 - weft_idx
        y = svg_row * cell_px
        rows.append(f'<rect x="0" y="{y}" width="{total_w}" height="{cell_px}" fill="{weft_css}"/>')
        rows.append(f'<use href="#s{sid}" x="0" y="{y}"/>')

    # Single <path> whose sub-paths outline each visible float — borders only at
    # float edges, never inside a multi-cell float.
    border_parts: list[str] = []
    for start, end, visible, _length, _thread in draft.compute_floats():
        if not visible:
            continue
        svg_x = start[0] * cell_px
        svg_y = (weft_count - 1 - end[1]) * cell_px
        w = (end[0] - start[0] + 1) * cell_px
        h = (end[1] - start[1] + 1) * cell_px
        border_parts.append(f"M{svg_x} {svg_y}h{w}v{h}h{-w}z")

    border = f'<path d="{"".join(border_parts)}" stroke="#7f7f7f" stroke-width="0.5" fill="none"/>'

    defs = f"<defs>{''.join(symbol_defs)}</defs>"
    body = "".join(rows)
    return (
        f'<svg width="{total_w}" height="{total_h}"'
        f' viewBox="0 0 {total_w} {total_h}"'
        f' xmlns="http://www.w3.org/2000/svg"'
        f' xmlns:xlink="http://www.w3.org/1999/xlink">'
        f"{defs}{body}{border}</svg>"
    )


def drawdown_data(draft, cell_px: int = 20) -> dict:
    """Return float geometry as a plain dict ready for JSON serialisation.

    Each entry in ``floats`` is ``[x, y, w, h, color_hex]`` with y-coordinates
    flipped so that the last pick is at y=0 (top) — matching the orientation of
    ``drawdown_svg()`` and the PNG tile renderer.

    Suitable for client-side canvas rendering: fill each float in pass 1, then
    stroke all outlines via a single Path2D in pass 2.
    """
    weft_count = len(draft.weft)
    floats: list[list] = []
    for start, end, visible, _length, thread in draft.compute_floats():
        if not visible:
            continue
        x = int(start[0]) * cell_px
        y = (weft_count - 1 - int(end[1])) * cell_px
        w = (int(end[0]) - int(start[0]) + 1) * cell_px
        h = (int(end[1]) - int(start[1]) + 1) * cell_px
        if thread.color:
            r, g, b = thread.color.rgb
            color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        else:
            color = "#ffffff"
        floats.append([x, y, w, h, color])
    return {
        "cell_px": cell_px,
        "warp_count": len(draft.warp),
        "weft_count": weft_count,
        "floats": floats,
    }
