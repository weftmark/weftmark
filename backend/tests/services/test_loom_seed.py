"""Tests for app.services.loom_seed — JSON read helper (S7493, #957)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.loom_seed import _read_json, seed


class TestReadJson:
    def test_reads_json_list(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps([{"brand": "Example"}]))
        assert _read_json(p) == [{"brand": "Example"}]

    def test_reads_json_dict_with_looms_key(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"looms": [{"brand": "Example"}]}))
        assert _read_json(p) == {"looms": [{"brand": "Example"}]}


class _FakeSession:
    """Minimal stand-in supporting the `async with session_factory() as session:`
    / `async with session.begin():` shape used by seed()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def begin(self):
        return self


class TestSeedOffloadsJsonRead:
    async def test_seed_reads_json_via_thread(self, tmp_path, monkeypatch):
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"looms": []}))
        monkeypatch.setattr("app.services.loom_seed.locate_json", lambda: p)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine),
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=lambda: _FakeSession()),
        ):
            result = await seed()

        assert result == {"inserted": 0, "updated": 0, "skipped": 0}
