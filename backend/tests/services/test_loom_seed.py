"""Tests for app.services.loom_seed — JSON read helper (S7493, #957)."""

import json

from app.services.loom_seed import _read_json


class TestReadJson:
    def test_reads_json_list(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps([{"brand": "Example"}]))
        assert _read_json(p) == [{"brand": "Example"}]

    def test_reads_json_dict_with_looms_key(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"looms": [{"brand": "Example"}]}))
        assert _read_json(p) == {"looms": [{"brand": "Example"}]}
