# Copyright 2014-2015 Scott Torborg (storborg@gmail.com) — MIT License
# Vendored and modernised by WeftMark. See UPSTREAM_LICENSE for full text.
#
# Changes from upstream:
#   - Dropped Python 2/3 compat shims (from __future__ import, six dependency)
#   - configparser imported from stdlib (Python 3 standard)

from __future__ import annotations

from configparser import RawConfigParser

from app.weaving import Draft, __version__


class WIFReader:
    """Parse a WIF file into a Draft."""

    allowed_units = ("decipoints", "inches", "centimeters")

    def __init__(self, filename: str):
        self.filename = filename

    def getbool(self, section: str, option: str) -> bool:
        if self.config.has_option(section, option):
            return self.config.getboolean(section, option)
        return False

    def put_metadata(self, draft: Draft) -> None:
        draft.date = self.config.get("WIF", "Date")

    def put_warp(self, draft: Draft, wif_palette: dict) -> None:
        warp_thread_count = self.config.getint("WARP", "Threads")
        warp_units = self.config.get("WARP", "Units").lower()
        assert warp_units in self.allowed_units, f"Warp Units of {warp_units!r} is not understood"

        has_warp_colors = self.getbool("CONTENTS", "WARP COLORS")
        warp_color_map: dict[int, int] | None = None
        if has_warp_colors:
            warp_color_map = {}
            for thread_no, value in self.config.items("WARP COLORS"):
                warp_color_map[int(thread_no)] = int(value)

        warp_color = None
        if not warp_color_map:
            has_warp_colors = False
            warp_color = self.config.getint("WARP", "Color")

        has_threading = self.getbool("CONTENTS", "THREADING")
        threading_map: dict[int, list[int]] = {}
        if has_threading:
            for thread_no, value in self.config.items("THREADING"):
                threading_map[int(thread_no)] = [int(sn) for sn in value.split(",")]

        for thread_no in range(1, warp_thread_count + 1):
            if thread_no not in threading_map:
                continue
            color = wif_palette.get(warp_color_map[thread_no] if has_warp_colors else warp_color, [0, 0, 0])
            shaft = None
            if has_threading:
                shafts = {draft.shafts[sn - 1] for sn in threading_map[thread_no]}
                assert len(shafts) == 1
                shaft = next(iter(shafts))
            draft.add_warp_thread(color=color, shaft=shaft)

    def put_weft(self, draft: Draft, wif_palette: dict) -> None:
        weft_thread_count = self.config.getint("WEFT", "Threads")
        weft_units = self.config.get("WEFT", "Units").lower()
        assert weft_units in self.allowed_units, f"Weft Units of {weft_units!r} is not understood"

        has_weft_colors = self.getbool("CONTENTS", "WEFT COLORS")
        weft_color_map: dict[int, int] | None = None
        if has_weft_colors:
            weft_color_map = {}
            for thread_no, value in self.config.items("WEFT COLORS"):
                weft_color_map[int(thread_no)] = int(value)

        weft_color = None
        if not weft_color_map:
            has_weft_colors = False
            weft_color = self.config.getint("WEFT", "Color")

        has_liftplan = self.getbool("CONTENTS", "LIFTPLAN")
        liftplan_map: dict[int, list[int]] = {}
        if has_liftplan:
            for thread_no, value in self.config.items("LIFTPLAN"):
                liftplan_map[int(thread_no)] = [int(sn) for sn in value.split(",")]

        has_treadling = self.getbool("CONTENTS", "TREADLING")
        treadling_map: dict[int, list[int]] = {}
        if has_treadling:
            for thread_no, value in self.config.items("TREADLING"):
                try:
                    treadling_map[int(thread_no)] = [int(tn) for tn in value.split(",")]
                except ValueError:
                    pass

        for thread_no in range(1, weft_thread_count + 1):
            if not ((has_liftplan and thread_no in liftplan_map) or (has_treadling and thread_no in treadling_map)):
                continue
            color = wif_palette.get(weft_color_map[thread_no] if has_weft_colors else weft_color, [0, 0, 0])
            shafts = {draft.shafts[sn - 1] for sn in liftplan_map[thread_no]} if has_liftplan else set()
            treadles = {draft.treadles[tn - 1] for tn in treadling_map[thread_no]} if has_treadling else set()
            draft.add_weft_thread(color=color, shafts=shafts, treadles=treadles)

    def put_tieup(self, draft: Draft) -> None:
        for treadle_no, value in self.config.items("TIEUP"):
            treadle = draft.treadles[int(treadle_no) - 1]
            for shaft_no in (int(sn) for sn in value.split(",")):
                treadle.shafts.add(draft.shafts[shaft_no - 1])

    def read(self) -> Draft:
        self.config = RawConfigParser()
        self.config.read(self.filename)

        rising_shed = self.getbool("WEAVING", "Rising Shed")
        num_shafts = self.config.getint("WEAVING", "Shafts")
        num_treadles = self.config.getint("WEAVING", "Treadles")

        liftplan = self.getbool("CONTENTS", "LIFTPLAN")
        treadling = self.getbool("CONTENTS", "TREADLING")
        assert not (liftplan and treadling), "WIF contains both liftplan and treadling"
        assert not (liftplan and num_treadles > 0), "WIF contains liftplan and non-zero treadle count"

        if self.getbool("CONTENTS", "COLOR PALETTE"):
            rstart, rend = self.config.get("COLOR PALETTE", "Range").split(",")
            palette_range = int(rstart), int(rend)
        else:
            palette_range = 0, 255

        wif_palette: dict[int, list[int]] = {}
        if self.getbool("CONTENTS", "COLOR TABLE"):
            for color_no, value in self.config.items("COLOR TABLE"):
                channels = [int(ch) for ch in value.split(",")]
                channels = [int(round(ch * (255.0 / palette_range[1]))) for ch in channels]
                wif_palette[int(color_no)] = channels

        draft = Draft(num_shafts=num_shafts, num_treadles=num_treadles, rising_shed=rising_shed)
        self.put_metadata(draft)
        self.put_warp(draft, wif_palette)
        self.put_weft(draft, wif_palette)
        if treadling:
            self.put_tieup(draft)

        return draft


class WIFWriter:
    """Write a Draft to WIF format."""

    def __init__(self, draft: Draft):
        self.draft = draft

    def write_metadata(self, config: RawConfigParser, liftplan: bool) -> None:
        config.add_section("WIF")
        config.set("WIF", "Date", self.draft.date)
        config.set("WIF", "Version", "1.1")
        config.set("WIF", "Developers", "storborg@gmail.com")
        config.set("WIF", "Source Program", "PyWeaving")
        config.set("WIF", "Source Version", __version__)

        config.set("CONTENTS", "WEAVING", 1)
        config.add_section("WEAVING")
        config.set("WEAVING", "Rising Shed", self.draft.rising_shed)
        config.set("WEAVING", "Shafts", len(self.draft.shafts))
        config.set("WEAVING", "Treadles", 0 if liftplan else len(self.draft.treadles))

        config.set("CONTENTS", "TEXT", 1)
        config.add_section("TEXT")
        config.set("TEXT", "Title", self.draft.title)
        config.set("TEXT", "Author", self.draft.author)
        config.set("TEXT", "Address", self.draft.address)
        config.set("TEXT", "EMail", self.draft.email)
        config.set("TEXT", "Telephone", self.draft.telephone)
        config.set("TEXT", "FAX", self.draft.fax)

        if self.draft.notes:
            config.set("CONTENTS", "NOTES", 1)
            config.add_section("NOTES")
            for ii, line in enumerate(self.draft.notes.split("\n")):
                config.set("NOTES", str(ii), line)

    def write_palette(self, config: RawConfigParser) -> dict:
        colors = set(thread.color.rgb for thread in self.draft.warp + self.draft.weft)
        wif_palette: dict = {}
        config.set("CONTENTS", "COLOR TABLE", 1)
        config.add_section("COLOR TABLE")
        for ii, color in enumerate(colors, start=1):
            config.set("COLOR TABLE", str(ii), f"{color[0]},{color[1]},{color[2]}")
            wif_palette[color] = ii

        config.set("CONTENTS", "COLOR PALETTE", 1)
        config.add_section("COLOR PALETTE")
        config.set("COLOR PALETTE", "Form", "RGB")
        config.set("COLOR PALETTE", "Range", "0,255")
        return wif_palette

    def write_threads(self, config: RawConfigParser, wif_palette: dict, dir: str) -> None:
        assert dir in ("warp", "weft")
        threads = getattr(self.draft, dir)
        dir_upper = dir.upper()
        config.set("CONTENTS", dir_upper, 1)
        config.add_section(dir_upper)
        config.set(dir_upper, "Threads", len(threads))
        config.set(dir_upper, "Units", "Inches")

        config.set("CONTENTS", f"{dir_upper} COLORS", 1)
        config.add_section(f"{dir_upper} COLORS")
        for ii, thread in enumerate(threads, start=1):
            config.set(f"{dir_upper} COLORS", str(ii), wif_palette[thread.color.rgb])

    def write_threading(self, config: RawConfigParser) -> None:
        config.set("CONTENTS", "THREADING", 1)
        config.add_section("THREADING")
        for ii, thread in enumerate(self.draft.warp, start=1):
            config.set("THREADING", str(ii), str(self.draft.shafts.index(thread.shaft) + 1))

    def write_liftplan(self, config: RawConfigParser) -> None:
        config.set("CONTENTS", "LIFTPLAN", 1)
        config.add_section("LIFTPLAN")
        for ii, thread in enumerate(self.draft.weft, start=1):
            shaft_nos = [self.draft.shafts.index(shaft) + 1 for shaft in thread.connected_shafts]
            config.set("LIFTPLAN", str(ii), ",".join(str(n) for n in shaft_nos))

    def write_treadling(self, config: RawConfigParser) -> None:
        config.set("CONTENTS", "TREADLING", 1)
        config.add_section("TREADLING")
        for ii, thread in enumerate(self.draft.weft, start=1):
            treadle_nos = [self.draft.treadles.index(tr) + 1 for tr in thread.treadles]
            config.set("TREADLING", str(ii), ",".join(str(n) for n in treadle_nos))

    def write_tieup(self, config: RawConfigParser) -> None:
        config.set("CONTENTS", "TIEUP", 1)
        config.add_section("TIEUP")
        for ii, treadle in enumerate(self.draft.treadles, start=1):
            shaft_nos = [self.draft.shafts.index(shaft) + 1 for shaft in treadle.shafts]
            config.set("TIEUP", str(ii), ",".join(str(n) for n in shaft_nos))

    def write(self, filename: str, liftplan: bool = False) -> None:
        assert self.draft.start_at_lowest_thread

        config = RawConfigParser()
        config.optionxform = str  # type: ignore[method-assign]
        config.add_section("CONTENTS")

        self.write_metadata(config, liftplan=liftplan)
        wif_palette = self.write_palette(config)
        self.write_threads(config, wif_palette, "warp")
        self.write_threads(config, wif_palette, "weft")
        self.write_threading(config)
        if liftplan or not self.draft.treadles:
            self.write_liftplan(config)
        else:
            self.write_treadling(config)
            self.write_tieup(config)

        with open(filename, "w", encoding="utf-8") as f:
            config.write(f)
