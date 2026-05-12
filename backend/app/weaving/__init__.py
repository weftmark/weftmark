# Copyright 2014-2015 Scott Torborg (storborg@gmail.com) — MIT License
# Vendored and modernised by WeftMark. See UPSTREAM_LICENSE for full text.
#
# Public API surface — only these names are part of the stable interface.
# Internal modules are prefixed with _ and should not be imported directly.

import datetime
import json
from collections import defaultdict
from copy import deepcopy

__version__ = "1.0.0"

__all__ = [
    "Color",
    "Draft",
    "DraftError",
    "Shaft",
    "Treadle",
    "WarpThread",
    "WeftThread",
]


class Color:
    """RGB colour; no transparency support."""

    def __init__(self, rgb):
        if not isinstance(rgb, tuple):
            rgb = tuple(rgb)
        self.rgb = rgb

    def __eq__(self, other):
        return self.rgb == other.rgb

    def __ne__(self, other):
        return self.rgb != other.rgb

    @property
    def css(self):
        return f"rgb({self.rgb[0]}, {self.rgb[1]}, {self.rgb[2]})"

    def __str__(self):
        return str(self.rgb)

    def __repr__(self):
        return f"Color({self.rgb!r})"


class WarpThread:
    """A single warp thread."""

    def __init__(self, color=None, shaft=None):
        if color and not isinstance(color, Color):
            color = Color(color)
        self.color = color
        self.shaft = shaft

    def __repr__(self):
        return f"<WarpThread color:{self.color.rgb} shaft:{self.shaft}>"


class WeftThread:
    """A single weft thread."""

    def __init__(self, color=None, shafts=None, treadles=None):
        if color and not isinstance(color, Color):
            color = Color(color)
        self.color = color
        assert not (shafts and treadles), "cannot specify both shafts (liftplan) and treadles"
        self.treadles = treadles or set()
        self.shafts = shafts or set()

    @property
    def connected_shafts(self):
        if self.shafts:
            return self.shafts
        assert self.treadles
        ret = set()
        for treadle in self.treadles:
            ret.update(treadle.shafts)
        return ret

    def __repr__(self):
        if self.treadles:
            return f"<WeftThread color:{self.color.rgb} treadles:{self.treadles}>"
        return f"<WeftThread color:{self.color.rgb} shafts:{self.shafts}>"


class Shaft:
    """A single loom shaft."""

    pass


class Treadle:
    """A single loom treadle."""

    def __init__(self, shafts=None):
        self.shafts = shafts or set()


class DraftError(Exception):
    pass


class Draft:
    """The core representation of a weaving draft."""

    def __init__(
        self,
        num_shafts,
        num_treadles=0,
        liftplan=False,
        rising_shed=True,
        start_at_lowest_thread=True,
        date=None,
        title="",
        author="",
        address="",
        email="",
        telephone="",
        fax="",
        notes="",
    ):
        self.liftplan = liftplan or (num_treadles == 0)
        self.rising_shed = rising_shed
        self.start_at_lowest_thread = start_at_lowest_thread

        self.shafts = [Shaft() for _ in range(num_shafts)]
        self.treadles = [Treadle() for _ in range(num_treadles)]

        self.warp: list[WarpThread] = []
        self.weft: list[WeftThread] = []

        self.date = date or datetime.date.today().strftime("%b %d, %Y")
        self.title = title
        self.author = author
        self.address = address
        self.email = email
        self.telephone = telephone
        self.fax = fax
        self.notes = notes

    @classmethod
    def from_json(cls, s: str) -> "Draft":
        """Construct a Draft from its JSON representation (counterpart to to_json)."""
        obj = json.loads(s)
        warp = obj.pop("warp")
        weft = obj.pop("weft")
        tieup = obj.pop("tieup")

        draft = cls(**obj)

        for thread_obj in warp:
            draft.add_warp_thread(color=thread_obj["color"], shaft=draft.shafts[thread_obj["shaft"]])

        for thread_obj in weft:
            draft.add_weft_thread(
                color=thread_obj["color"],
                shafts=set(draft.shafts[n] for n in thread_obj["shafts"]),
                treadles=set(draft.treadles[n] for n in thread_obj["treadles"]),
            )

        for ii, shaft_nos in enumerate(tieup):
            draft.treadles[ii].shafts = set(draft.shafts[n] for n in shaft_nos)

        return draft

    def to_json(self) -> str:
        """Serialize to JSON (counterpart to from_json)."""
        return json.dumps(
            {
                "liftplan": self.liftplan,
                "rising_shed": self.rising_shed,
                "num_shafts": len(self.shafts),
                "num_treadles": len(self.treadles),
                "warp": [{"color": thread.color.rgb, "shaft": self.shafts.index(thread.shaft)} for thread in self.warp],
                "weft": [
                    {
                        "color": thread.color.rgb,
                        "treadles": [self.treadles.index(tr) for tr in thread.treadles],
                        "shafts": [self.shafts.index(sh) for sh in thread.shafts],
                    }
                    for thread in self.weft
                ],
                "tieup": [[self.shafts.index(sh) for sh in treadle.shafts] for treadle in self.treadles],
                "date": self.date,
                "title": self.title,
                "author": self.author,
                "address": self.address,
                "email": self.email,
                "telephone": self.telephone,
                "fax": self.fax,
                "notes": self.notes,
            }
        )

    def copy(self) -> "Draft":
        return deepcopy(self)

    def add_warp_thread(self, color=None, index=None, shaft=0) -> None:
        if shaft is not None and not isinstance(shaft, Shaft):
            shaft = self.shafts[shaft]
        thread = WarpThread(color=color, shaft=shaft)
        if index is None:
            self.warp.append(thread)
        else:
            self.warp.insert(index, thread)

    def add_weft_thread(self, color=None, index=None, shafts=None, treadles=None) -> None:
        shafts = shafts or set()
        shaft_objs: set[Shaft] = set()
        for shaft in shafts:
            if not isinstance(shaft, Shaft):
                shaft = self.shafts[shaft]
            shaft_objs.add(shaft)
        treadles = treadles or set()
        treadle_objs: set[Treadle] = set()
        for treadle in treadles:
            if not isinstance(treadle, Treadle):
                treadle = self.treadles[treadle]
            treadle_objs.add(treadle)
        thread = WeftThread(color=color, shafts=shaft_objs, treadles=treadle_objs)
        if index is None:
            self.weft.append(thread)
        else:
            self.weft.insert(index, thread)

    def compute_drawdown_at(self, position: tuple[int, int]) -> WarpThread | WeftThread:
        x, y = position
        warp_thread = self.warp[x]
        weft_thread = self.weft[y]
        connected_shafts = weft_thread.connected_shafts
        warp_at_rest = warp_thread.shaft not in connected_shafts
        if warp_at_rest ^ self.rising_shed:
            return warp_thread
        return weft_thread

    def compute_drawdown(self) -> list[list[WarpThread | WeftThread]]:
        num_warp = len(self.warp)
        num_weft = len(self.weft)
        return [[self.compute_drawdown_at((x, y)) for y in range(num_weft)] for x in range(num_warp)]

    def compute_floats(self):
        """
        Yield ``(start, end, visible, length, thread)`` for every float.
        FIXME: ignores the back side of the fabric.
        """
        num_warp = len(self.warp)
        num_weft = len(self.weft)
        drawdown = self.compute_drawdown()

        for x, thread in enumerate(self.warp):
            this_vis = thread == drawdown[x][0]
            this_start = last = (x, 0)
            for y in range(1, num_weft):
                check_vis = thread == drawdown[x][y]
                if check_vis != this_vis:
                    yield this_start, last, this_vis, last[1] - this_start[1], thread
                    this_vis = check_vis
                    this_start = x, y
                last = x, y
            yield this_start, last, this_vis, last[1] - this_start[1], thread

        for y, thread in enumerate(self.weft):
            this_vis = thread == drawdown[0][y]
            this_start = last = (0, y)
            for x in range(1, num_warp):
                check_vis = thread == drawdown[x][y]
                if check_vis != this_vis:
                    yield this_start, last, this_vis, last[0] - this_start[0], thread
                    this_vis = check_vis
                    this_start = x, y
                last = x, y
            yield this_start, last, this_vis, last[0] - this_start[0], thread

    def compute_longest_floats(self) -> tuple[int, int]:
        """
        Return (longest_warp_float, longest_weft_float).
        FIXME: upstream noted this might produce incorrect results.
        """
        floats = list(self.compute_floats())
        warp_max = max(
            (length for _, _, _, length, thread in floats if isinstance(thread, WarpThread)),
            default=0,
        )
        weft_max = max(
            (length for _, _, _, length, thread in floats if isinstance(thread, WeftThread)),
            default=0,
        )
        return warp_max, weft_max

    def all_threads_attached(self) -> bool:
        """Return True if every warp thread has a shaft assignment."""
        return all(t.shaft is not None for t in self.warp)

    def reduce_shafts(self):
        raise NotImplementedError

    def reduce_treadles(self):
        raise NotImplementedError

    def reduce_active_treadles(self) -> None:
        if self.liftplan:
            raise ValueError("cannot reduce treadles on a liftplan draft")
        used_shaft_combos: dict = defaultdict(list)
        for thread in self.weft:
            used_shaft_combos[frozenset(thread.connected_shafts)].append(thread)
        self.treadles = []
        for shafts, threads in used_shaft_combos.items():
            treadle = Treadle(shafts=set(shafts))
            self.treadles.append(treadle)
            for thread in threads:
                thread.treadles = {treadle}

    def sort_threading(self):
        raise NotImplementedError

    def sort_treadles(self):
        raise NotImplementedError

    def invert_shed(self) -> None:
        self.rising_shed = not self.rising_shed
        for thread in self.weft:
            thread.shafts = self.shafts - thread.shafts  # type: ignore[assignment]
        for treadle in self.treadles:
            treadle.shafts = self.shafts - treadle.shafts  # type: ignore[assignment]

    def rotate(self):
        raise NotImplementedError

    def flip_weftwise(self) -> None:
        self.warp.reverse()

    def flip_warpwise(self) -> None:
        self.weft.reverse()

    def selvedges_continuous(self) -> bool:
        return self.selvedge_continuous(False) and self.selvedge_continuous(True)

    def selvedge_continuous(self, low: bool) -> bool:
        offset = 0 if low ^ self.start_at_lowest_thread else 1
        thread = self.warp[0] if low else self.warp[-1]
        for ii in range(offset, len(self.weft) - 1, 2):
            a_state = thread.shaft in self.weft[ii].connected_shafts
            b_state = thread.shaft in self.weft[ii + 1].connected_shafts
            if not a_state ^ b_state:
                return False
        return True

    def make_selvedges_continuous(self, add_new_shafts: bool = False) -> None:
        for low_thread in (False, True):
            success = False
            warp_thread = self.warp[0] if low_thread else self.warp[-1]
            if self.selvedge_continuous(low_thread):
                success = True
                continue
            for shaft in self.shafts:
                warp_thread.shaft = shaft
                if self.selvedge_continuous(low_thread):
                    success = True
                    break
            if not success:
                if add_new_shafts:
                    raise NotImplementedError
                raise DraftError("cannot make continuous selvedges")

    def compute_weft_crossings(self):
        raise NotImplementedError

    def compute_warp_crossings(self):
        raise NotImplementedError

    def repeat(self, n: int) -> None:
        initial_warp = list(self.warp)
        initial_weft = list(self.weft)
        for _ in range(n):
            for thread in initial_warp:
                self.add_warp_thread(color=thread.color, shaft=thread.shaft)
            for thread in initial_weft:
                self.add_weft_thread(color=thread.color, treadles=thread.treadles, shafts=thread.shafts)
