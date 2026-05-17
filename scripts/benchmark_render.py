"""
Benchmark rendering strategies across all WIF files.

Strategies compared:
  A  PNG full draft        (ImageRenderer — current full-draft view)
  B  PNG drawdown only     (cropped from A — current project activity view)
  C  SVG full draft        (SVGRenderer — candidate for full-draft view)
  D  SVG drawdown deduped  (symbol-per-unique-row — candidate for project activity)

Outputs a CSV and summary text to scripts/benchmarkout/<datetime>_results.csv
and scripts/benchmarkout/<datetime>_summary.txt.
"""

from __future__ import annotations

import csv
import gzip
import io
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from PIL import Image as PILImage

sys.path.insert(0, "/app")
os.environ.setdefault("POSTGRES_PASSWORD", "x")  # silence settings import

from app.weaving import Draft
from app.weaving._render import ImageRenderer, SVGRenderer
from app.weaving._wif import WIFReader

SCALE = 10
MARGIN = 20


# ---------------------------------------------------------------------------
# Strategy D: symbol-deduped drawdown-only SVG
# ---------------------------------------------------------------------------

def make_deduped_drawdown_svg(draft: Draft, scale: int = SCALE) -> str:
    drawdown = draft.compute_drawdown()
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)

    # Group rows by their colour pattern (identical rows share a symbol)
    pattern_to_id: dict[tuple, str] = {}
    symbol_defs: list[str] = []
    use_refs: list[str] = []

    for y in range(weft_count):
        pattern = tuple(drawdown[x][y].color.rgb for x in range(warp_count))
        if pattern not in pattern_to_id:
            sid = f"r{len(pattern_to_id)}"
            pattern_to_id[pattern] = sid
            rects = "".join(
                f'<rect x="{x * scale}" y="0" width="{scale}" height="{scale}" fill="rgb{c}"/>'
                for x, c in enumerate(pattern)
            )
            symbol_defs.append(f'<symbol id="{sid}">{rects}</symbol>')
        use_refs.append(f'<use href="#{pattern_to_id[pattern]}" y="{y * scale}"/>')

    w = warp_count * scale
    h = weft_count * scale
    defs = "".join(symbol_defs)
    uses = "".join(use_refs)
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}">'
        f"<defs>{defs}</defs>{uses}</svg>"
    )


# ---------------------------------------------------------------------------
# Strategy B helper: crop drawdown from full PIL image
# ---------------------------------------------------------------------------

def crop_drawdown_png(draft: Draft, full_im: PILImage.Image, scale: int) -> bytes:
    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    offsetx = MARGIN
    offsety = MARGIN + (6 + len(draft.shafts)) * scale
    w = warp_count * scale
    h = weft_count * scale
    cropped = full_im.crop((offsetx, offsety, offsetx + w, offsety + h))
    cropped = cropped.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Benchmark one file
# ---------------------------------------------------------------------------

class Row(NamedTuple):
    path: str
    warp: int
    weft: int
    treadles: int
    unique_rows: int
    dedup_ratio: float
    # sizes (bytes)
    png_full_sz: int
    png_dd_sz: int
    svg_full_sz: int
    svg_dd_sz: int
    png_full_gz: int
    png_dd_gz: int
    svg_full_gz: int
    svg_dd_gz: int
    # times (ms)
    png_full_ms: float
    png_dd_ms: float
    svg_full_ms: float
    svg_dd_ms: float
    error: str


def gz(data: bytes | str) -> int:
    raw = data if isinstance(data, bytes) else data.encode()
    return len(gzip.compress(raw, compresslevel=6))


def bench(wif_path: str) -> Row:
    label = Path(wif_path).name
    try:
        draft = WIFReader(wif_path).read()
    except Exception as e:
        return Row(label, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, str(e))

    warp_count = len(draft.warp)
    weft_count = len(draft.weft)
    treadle_count = len(draft.treadles)

    if warp_count == 0 or weft_count == 0:
        return Row(label, warp_count, weft_count, treadle_count, 0, 0.0,
                   0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "empty draft")

    # Count unique row patterns
    try:
        dd = draft.compute_drawdown()
        patterns: set[tuple] = set()
        for y in range(weft_count):
            patterns.add(tuple(dd[x][y].color.rgb for x in range(warp_count)))
        unique_rows = len(patterns)
        dedup_ratio = round(unique_rows / weft_count, 4)
    except Exception:
        unique_rows = 0
        dedup_ratio = 0.0

    errors = []

    # Strategy A: PNG full draft
    try:
        t0 = time.perf_counter()
        renderer = ImageRenderer(draft, scale=SCALE, margin_pixels=MARGIN)
        full_im = renderer.make_pil_image()
        buf = io.BytesIO()
        full_im.save(buf, format="PNG")
        png_full_bytes = buf.getvalue()
        png_full_ms = (time.perf_counter() - t0) * 1000
        png_full_sz = len(png_full_bytes)
        png_full_gz = gz(png_full_bytes)
    except Exception as e:
        errors.append(f"PNG-full:{e}")
        full_im = None
        png_full_ms = png_full_sz = png_full_gz = 0

    # Strategy B: PNG drawdown crop
    try:
        t0 = time.perf_counter()
        if full_im is None:
            renderer = ImageRenderer(draft, scale=SCALE, margin_pixels=MARGIN)
            full_im = renderer.make_pil_image()
        dd_png_bytes = crop_drawdown_png(draft, full_im, SCALE)
        png_dd_ms = (time.perf_counter() - t0) * 1000
        png_dd_sz = len(dd_png_bytes)
        png_dd_gz = gz(dd_png_bytes)
    except Exception as e:
        errors.append(f"PNG-dd:{e}")
        png_dd_ms = png_dd_sz = png_dd_gz = 0

    # Strategy C: SVG full draft
    try:
        t0 = time.perf_counter()
        svg_renderer = SVGRenderer(draft, scale=SCALE)
        svg_full_str = svg_renderer.render_to_string()
        svg_full_ms = (time.perf_counter() - t0) * 1000
        svg_full_sz = len(svg_full_str.encode())
        svg_full_gz = gz(svg_full_str)
    except Exception as e:
        errors.append(f"SVG-full:{e}")
        svg_full_ms = svg_full_sz = svg_full_gz = 0

    # Strategy D: symbol-deduped drawdown SVG
    try:
        t0 = time.perf_counter()
        svg_dd_str = make_deduped_drawdown_svg(draft, SCALE)
        svg_dd_ms = (time.perf_counter() - t0) * 1000
        svg_dd_sz = len(svg_dd_str.encode())
        svg_dd_gz = gz(svg_dd_str)
    except Exception as e:
        errors.append(f"SVG-dd:{e}")
        svg_dd_ms = svg_dd_sz = svg_dd_gz = 0

    return Row(
        path=label,
        warp=warp_count,
        weft=weft_count,
        treadles=treadle_count,
        unique_rows=unique_rows,
        dedup_ratio=dedup_ratio,
        png_full_sz=png_full_sz,
        png_dd_sz=png_dd_sz,
        svg_full_sz=svg_full_sz,
        svg_dd_sz=svg_dd_sz,
        png_full_gz=png_full_gz,
        png_dd_gz=png_dd_gz,
        svg_full_gz=svg_full_gz,
        svg_dd_gz=svg_dd_gz,
        png_full_ms=round(png_full_ms, 1),
        png_dd_ms=round(png_dd_ms, 1),
        svg_full_ms=round(svg_full_ms, 1),
        svg_dd_ms=round(svg_dd_ms, 1),
        error="; ".join(errors),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_wif_files(*roots: str) -> list[str]:
    files = []
    for root in roots:
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fn.lower().endswith(".wif"):
                    files.append(os.path.join(dirpath, fn))
    return sorted(files)


def fmt_kb(n: int) -> str:
    return f"{n/1024:.1f}KB"


def _build_summary(rows: list[Row]) -> str:
    ok = [r for r in rows if not r.error and r.warp > 0]
    lines: list[str] = []

    lines.append(f"=== SUMMARY ({len(ok)}/{len(rows)} files rendered) ===")

    def avg(vals: list) -> float:
        return sum(vals) / len(vals) if vals else 0

    def med(vals: list) -> float:
        s = sorted(vals)
        return s[len(s) // 2] if s else 0

    for label, szs, gzs, mss in [
        ("PNG full draft  (A)", [r.png_full_sz for r in ok], [r.png_full_gz for r in ok], [r.png_full_ms for r in ok]),
        ("PNG drawdown    (B)", [r.png_dd_sz for r in ok], [r.png_dd_gz for r in ok], [r.png_dd_ms for r in ok]),
        ("SVG full draft  (C)", [r.svg_full_sz for r in ok], [r.svg_full_gz for r in ok], [r.svg_full_ms for r in ok]),
        ("SVG deduped dd  (D)", [r.svg_dd_sz for r in ok], [r.svg_dd_gz for r in ok], [r.svg_dd_ms for r in ok]),
    ]:
        lines.append(
            f"{label}  "
            f"avg-size={fmt_kb(int(avg(szs)))}  med-size={fmt_kb(int(med(szs)))}  "
            f"avg-gz={fmt_kb(int(avg(gzs)))}  med-gz={fmt_kb(int(med(gzs)))}  "
            f"avg-render={avg(mss):.1f}ms  med-render={med(mss):.1f}ms"
        )

    lines.append(
        f"\nUnique-row dedup ratio  avg={avg([r.dedup_ratio for r in ok]):.3f}  "
        f"med={med([r.dedup_ratio for r in ok]):.3f}  "
        f"(lower = more dedup benefit)"
    )

    lines.append("\nLargest drawdowns (by weft count):")
    for r in sorted(ok, key=lambda r: r.weft, reverse=True)[:10]:
        lines.append(
            f"  {r.path[:55]:<55}  {r.warp}w×{r.weft}p  "
            f"treadles={r.treadles}  unique_rows={r.unique_rows}  "
            f"PNG-dd={fmt_kb(r.png_dd_gz)}gz  SVG-dd={fmt_kb(r.svg_dd_gz)}gz  "
            f"ratio={r.dedup_ratio:.3f}"
        )

    return "\n".join(lines)


def main() -> None:
    roots = ["/tmp/wif/test-wif-files", "/tmp/wif/docs-samples"]
    files = find_wif_files(*roots)
    print(f"Found {len(files)} WIF files", file=sys.stderr)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(__file__).parent / "benchmarkout"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"{ts}_results.csv"
    summary_path = out_dir / f"{ts}_summary.txt"

    rows: list[Row] = []
    with csv_path.open("w", newline="") as csv_fh:
        writer = csv.writer(csv_fh)
        writer.writerow(Row._fields)
        for i, path in enumerate(files, 1):
            r = bench(path)
            rows.append(r)
            writer.writerow(r)
            csv_fh.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(files)} done", file=sys.stderr)

    summary = _build_summary(rows)
    summary_path.write_text(summary)

    print(summary, file=sys.stderr)
    print(f"\nResults written to:\n  {csv_path}\n  {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
