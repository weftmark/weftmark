"""Tests for config_file path-traversal guard (S2083)."""

import os
from unittest.mock import patch

import pytest

from app.services.config_file import load, save

_KEY = "any-non-secret-key"  # only used for non-SECRET_FIELDS values; no Fernet needed


class TestAssertSafePath:
    def test_save_valid_path_succeeds(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _KEY, {"smtp_host": "smtp.example.com"})
        assert (tmp_path / "weftmark_config.json").exists()

    def test_load_valid_path_returns_empty_when_absent(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            result = load(config_path, _KEY)
        assert result == {}

    def test_save_rejects_traversal_path(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        traversal = str(tmp_path / ".." / "evil.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            with pytest.raises(ValueError, match="outside allowed root"):
                save(traversal, _KEY, {"smtp_host": "x"})

    def test_load_rejects_traversal_path(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        traversal = str(tmp_path / ".." / "evil.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            with pytest.raises(ValueError, match="outside allowed root"):
                load(traversal, _KEY)

    def test_save_rejects_path_outside_configured_root(self, tmp_path):
        config_root = tmp_path / "config"
        config_path = str(config_root / "weftmark_config.json")
        other_path = str(tmp_path / "other" / "config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            with pytest.raises(ValueError, match="outside allowed root"):
                save(other_path, _KEY, {})

    def test_save_roundtrip_preserves_plain_field(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _KEY, {"smtp_host": "mail.example.com"})
            result = load(config_path, _KEY)
        assert result["smtp_host"] == "mail.example.com"

    def test_save_removes_field_on_empty_string(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _KEY, {"smtp_host": "mail.example.com"})
            save(config_path, _KEY, {"smtp_host": ""})
            result = load(config_path, _KEY)
        assert "smtp_host" not in result
