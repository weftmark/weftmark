from pathlib import Path

_here = Path(__file__).parent  # .../app/

# Docker: /app/VERSION  |  local dev: repo root (two levels up from backend/app/)
for _candidate in [
    _here.parent / "VERSION",
    _here.parent.parent / "VERSION",
]:
    if _candidate.exists():
        VERSION = _candidate.read_text().strip()
        break
else:
    VERSION = "0.0.0"
