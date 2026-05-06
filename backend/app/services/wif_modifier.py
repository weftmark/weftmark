"""
Modify WIF file bytes in place (non-destructive — callers always write to
wif_modified_path, never to wif_path).

Currently supports:
  - set_weaving_int: update a single integer key in [WEAVING] (e.g. Treadles, Shafts)
  - zero_treadles_for_liftplan: normalise liftplan-only files that carry stale Treadles= metadata
"""

from __future__ import annotations

import re


def set_weaving_int(wif_bytes: bytes, key: str, value: int) -> bytes:
    """Return new WIF bytes with `key=value` set in the [WEAVING] section.

    If the key already exists it is replaced; if it is absent it is appended
    at the end of the [WEAVING] block. Works on the raw bytes to avoid
    configparser re-serialisation changing formatting or encoding.
    """
    try:
        text = wif_bytes.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = wif_bytes.decode("latin-1")
        encoding = "latin-1"

    # Replace existing key=... line inside [WEAVING] (case-insensitive key)
    pattern = re.compile(
        r"(?m)^(" + re.escape(key) + r"\s*=\s*).*$",
        re.IGNORECASE,
    )

    # Check if [WEAVING] section exists
    weaving_section = re.search(r"(?im)^\[WEAVING\]", text)
    if not weaving_section:
        raise ValueError("WIF file has no [WEAVING] section")

    if pattern.search(text):
        # Replace the existing line
        updated = pattern.sub(lambda m: f"{key}={value}", text, count=1)
    else:
        # Append the key after the [WEAVING] header line
        updated = re.sub(
            r"(?im)(^\[WEAVING\][^\n]*\n)",
            lambda m: m.group(0) + f"{key}={value}\n",
            text,
            count=1,
        )

    return updated.encode(encoding)


def zero_treadles_for_liftplan(wif_bytes: bytes) -> bytes:
    """Return normalised WIF bytes for files that mix liftplan data with stale treadle metadata.

    Some tools (e.g. TempoWeave Designer) write Treadles=N in [WEAVING] as informational
    metadata even in pure liftplan files. PyWeaving rejects this combination with an
    AssertionError. If the file has a [LIFTPLAN] section but no [TREADLING] section,
    set Treadles=0 so PyWeaving can parse it correctly.
    """
    try:
        text = wif_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = wif_bytes.decode("latin-1")

    has_liftplan = bool(re.search(r"(?im)^\[LIFTPLAN\]", text))
    has_treadling = bool(re.search(r"(?im)^\[TREADLING\]", text))

    if has_liftplan and not has_treadling:
        return set_weaving_int(wif_bytes, "Treadles", 0)
    return wif_bytes
