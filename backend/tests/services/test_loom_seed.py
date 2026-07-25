"""Tests for app.services.loom_seed — JSON read helper (S7493, #957) and
cognitive-complexity refactor of _coerce_entry/seed (S3776, #1063)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.loom_seed import (
    _coerce_array,
    _coerce_entry,
    _extract_entries,
    _read_json,
    _upsert_row,
    seed,
)


class TestReadJson:
    def test_reads_json_list(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps([{"brand": "Example"}]))
        assert _read_json(p) == [{"brand": "Example"}]

    def test_reads_json_dict_with_looms_key(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"looms": [{"brand": "Example"}]}))
        assert _read_json(p) == {"looms": [{"brand": "Example"}]}


class TestCoerceArray:
    def test_filters_non_numeric_values(self):
        assert _coerce_array([4, 6, "bad", None, 8.5]) == [4, 6, 8.5]

    def test_non_list_input_returns_none(self):
        assert _coerce_array("not a list") is None
        assert _coerce_array(None) is None

    def test_empty_after_filtering_returns_none(self):
        assert _coerce_array(["a", "b", None]) is None
        assert _coerce_array([]) is None


class TestCoerceEntry:
    def test_skips_underscore_metadata_fields(self):
        row = _coerce_entry({"_brand": "meta", "_confidence": 0.9, "brand": "AVL"})
        assert "_brand" not in row
        assert "_confidence" not in row
        assert row["brand"] == "AVL"

    def test_drops_unknown_columns(self):
        row = _coerce_entry({"brand": "AVL", "totally_unknown_field": 123})
        assert "totally_unknown_field" not in row
        assert row["brand"] == "AVL"

    def test_array_field_coerced_via_coerce_array(self):
        row = _coerce_entry({"shaft_count_options": [4, "bad", 8]})
        assert row["shaft_count_options"] == [4, 8]

    def test_array_field_non_list_becomes_none(self):
        row = _coerce_entry({"shaft_count_options": "not a list"})
        assert row["shaft_count_options"] is None

    def test_non_array_dict_or_list_becomes_none(self):
        row = _coerce_entry({"brand": {"nested": "object"}})
        assert row["brand"] is None
        row = _coerce_entry({"brand": ["a", "list"]})
        assert row["brand"] is None


class TestExtractEntries:
    def test_dict_with_looms_key(self):
        assert _extract_entries({"looms": [{"brand": "A"}]}) == [{"brand": "A"}]

    def test_bare_list(self):
        assert _extract_entries([{"brand": "A"}]) == [{"brand": "A"}]

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError, match="Unexpected JSON structure"):
            _extract_entries({"no_looms_key": True})
        with pytest.raises(ValueError, match="Unexpected JSON structure"):
            _extract_entries("just a string")


class _FakeSessionForUpsert:
    def __init__(self, existing_id: str | None):
        self.scalar = AsyncMock(return_value=existing_id)
        self.execute = AsyncMock()


class TestUpsertRow:
    async def test_missing_brand_returns_skipped(self):
        session = _FakeSessionForUpsert(existing_id=None)
        outcome = await _upsert_row(session, {"model_name": "Model X"})
        assert outcome == "skipped"
        session.execute.assert_not_called()

    async def test_missing_model_returns_skipped(self):
        session = _FakeSessionForUpsert(existing_id=None)
        outcome = await _upsert_row(session, {"brand": "AVL"})
        assert outcome == "skipped"
        session.execute.assert_not_called()

    async def test_new_row_inserts(self):
        session = _FakeSessionForUpsert(existing_id=None)
        outcome = await _upsert_row(session, {"brand": "AVL", "model_name": "Baby Wolf"})
        assert outcome == "inserted"
        session.execute.assert_awaited_once()
        sql = str(session.execute.call_args[0][0])
        assert "INSERT INTO loom_references" in sql

    async def test_existing_row_updates(self):
        session = _FakeSessionForUpsert(existing_id="existing-uuid")
        outcome = await _upsert_row(session, {"brand": "AVL", "model_name": "Baby Wolf", "shaft_count_options": [4, 8]})
        assert outcome == "updated"
        session.execute.assert_awaited_once()
        sql = str(session.execute.call_args[0][0])
        assert "UPDATE loom_references SET" in sql

    async def test_existing_row_with_no_other_fields_skips_execute_but_still_updated(self):
        session = _FakeSessionForUpsert(existing_id="existing-uuid")
        outcome = await _upsert_row(session, {"brand": "AVL", "model_name": "Baby Wolf"})
        assert outcome == "updated"
        session.execute.assert_not_called()


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
