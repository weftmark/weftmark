import os
import shutil
from pathlib import Path

import pytest
import pyweaving.render as _pwr


def _patch_pyweaving_font() -> None:
    """Copy a system font into PyWeaving's data dir if the expected file is missing."""
    data_dir = Path(os.path.dirname(_pwr.__file__)) / "data"
    target = data_dir / "Arial.ttf"
    if target.exists():
        return

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),  # Linux CI
        Path("C:/Windows/Fonts/Arial.ttf"),  # Windows
        Path("C:/Windows/Fonts/calibri.ttf"),  # Windows fallback
        Path("/System/Library/Fonts/Helvetica.ttc"),  # macOS
    ]
    for src in candidates:
        if src.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, target)
            return

    pytest.skip("No suitable system font found to patch PyWeaving — skipping render tests")


_patch_pyweaving_font()
