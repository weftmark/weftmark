# Copyright 2014-2015 Scott Torborg (storborg@gmail.com) — MIT License
# Vendored and modernised by WeftMark. See UPSTREAM_LICENSE for full text.

import re

from app.weaving import Draft

_COLOR_MAP = {
    "A": (92, 140, 168),
    "G": (0, 104, 24),
    "B": (44, 44, 128),
    "K": (0, 0, 0),
    "W": (224, 224, 224),
    "Y": (232, 192, 0),
    "R": (200, 0, 44),
    "P": (120, 0, 120),
    "C": (208, 80, 84),
    "LP": (180, 104, 172),
}


def tartan(sett: str, repeats: int = 1) -> Draft:
    """Generate a tartan draft from a sett string (e.g. 'B24, K4, G36')."""
    colors = []
    for piece in sett.split(", "):
        m = re.match(r"([A-Z]+)(\d+)", piece)
        if m:
            colors.append((_COLOR_MAP[m.group(1)], int(m.group(2))))

    colors = colors + list(reversed(colors))

    draft = Draft(num_shafts=4, num_treadles=4)
    for ii in range(4):
        draft.treadles[3 - ii].shafts.add(draft.shafts[ii])
        draft.treadles[3 - ii].shafts.add(draft.shafts[(ii + 1) % 4])

    thread_no = 0
    for _ in range(repeats):
        for color, count in colors:
            for _ in range(count):
                draft.add_warp_thread(color=color, shaft=thread_no % 4)
                draft.add_weft_thread(color=color, treadles=[thread_no % 4])
                thread_no += 1

    return draft
