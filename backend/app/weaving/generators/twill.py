# Copyright 2014-2015 Scott Torborg (storborg@gmail.com) — MIT License
# Vendored and modernised by WeftMark. See UPSTREAM_LICENSE for full text.

from app.weaving import Draft


def twill(size: int = 2, warp_color=(0, 0, 100), weft_color=(255, 255, 255)) -> Draft:
    """Generate a twill draft. size=2 → 2/2 twill, size=3 → 3/3 twill, etc."""
    shafts = 2 * size
    draft = Draft(num_shafts=shafts, num_treadles=shafts)

    for ii in range(shafts):
        for jj in range(size):
            draft.treadles[ii].shafts.add(draft.shafts[(ii + jj) % shafts])

    for ii in range(8 * size):
        draft.add_warp_thread(color=warp_color, shaft=ii % shafts)
        draft.add_weft_thread(color=weft_color, treadles=[ii % shafts])

    return draft
