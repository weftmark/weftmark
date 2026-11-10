"""Structural fingerprints for draft threading, tie-up, and drawdown (#983).

Exact-match only (v1) — a draft shifted/rotated by N threads or shafts will
not fingerprint-match an otherwise-identical draft. Rotation/transposition
aware comparison is deliberately out of scope for now.

threading_fingerprint / tieup_fingerprint hash the raw [THREADING] / [TIEUP]
structure directly — cheap, computed synchronously at WIF upload time.

drawdown_fingerprint hashes the full warp x weft interlacement grid, which is
derived from threading + tie-up + treadling/liftplan combined. Two WIFs can
permute the treadle-to-shaft [TIEUP] mapping and compensate with a different
[TREADLING] sequence, producing different threading/tie-up fingerprints but
an identical physical fabric — only the drawdown fingerprint catches that
"same fabric, different encoding" case. It is O(warp x weft) so it is
computed asynchronously (see app.tasks.fingerprint), not here.
"""

import hashlib
import json

from app.services import wif_parser


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_threading_fingerprint(wif_bytes: bytes) -> str | None:
    """sha256 of the canonicalized [THREADING] structure, or None if absent/degenerate."""
    try:
        data = wif_parser.parse_threading(wif_bytes)
    except ValueError:
        return None
    threading = [sorted(shafts) for shafts in data.threading]
    if not any(threading):
        return None
    return _hash(json.dumps(threading, separators=(",", ":")))


def compute_tieup_fingerprint(wif_bytes: bytes) -> str | None:
    """sha256 of the canonicalized [TIEUP] structure, or None if absent/degenerate."""
    try:
        data = wif_parser.parse_tieup(wif_bytes)
    except ValueError:
        return None
    if not any(data.tieup):
        return None
    return _hash(json.dumps(data.tieup, separators=(",", ":")))


def compute_drawdown_fingerprint(wif_bytes: bytes) -> str | None:
    """sha256 of the full warp x weft interlacement grid, or None if empty.

    Expensive (O(warp x weft)) — callers should invoke this from a background
    task, not inline in a request handler. See app.tasks.fingerprint.
    """
    from app.services import rendering
    from app.weaving import WarpThread

    draft = rendering.load_draft(wif_bytes)
    warp_n = len(draft.warp)
    weft_n = len(draft.weft)
    if warp_n == 0 or weft_n == 0:
        return None

    grid = draft.compute_drawdown()
    columns = ["".join("1" if isinstance(cell, WarpThread) else "0" for cell in column) for column in grid]
    payload = f"{warp_n}x{weft_n}:" + "|".join(columns)
    return _hash(payload)
