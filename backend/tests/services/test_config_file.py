"""Tests for config_file: path-traversal guard, encryption, load/save edge cases."""

import json
import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.services.config_file import decrypt, encrypt, load, save, sync_env_to_file

_KEY = "any-non-secret-key"  # only used for non-SECRET_FIELDS values; no Fernet needed
_FERNET_KEY = Fernet.generate_key().decode()  # valid Fernet key for secret-field tests


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

    def test_save_removes_field_on_none_value(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _KEY, {"smtp_host": "mail.example.com"})
            save(config_path, _KEY, {"smtp_host": None})
            result = load(config_path, _KEY)
        assert "smtp_host" not in result


# ---------------------------------------------------------------------------
# encrypt / decrypt
# ---------------------------------------------------------------------------


class TestEncryptDecrypt:
    def test_encrypt_returns_string(self):
        token = encrypt("my-secret", _FERNET_KEY)
        assert isinstance(token, str)
        assert token != "my-secret"

    def test_decrypt_roundtrip(self):
        token = encrypt("my-secret", _FERNET_KEY)
        assert decrypt(token, _FERNET_KEY) == "my-secret"

    def test_different_keys_fail_to_decrypt(self):
        other_key = Fernet.generate_key().decode()
        token = encrypt("my-secret", _FERNET_KEY)
        from cryptography.fernet import InvalidToken

        with pytest.raises((InvalidToken, Exception)):
            decrypt(token, other_key)


# ---------------------------------------------------------------------------
# load — edge cases
# ---------------------------------------------------------------------------


class TestLoadEdgeCases:
    def test_load_corrupt_file_returns_empty(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        (tmp_path / "weftmark_config.json").write_text("not valid json", encoding="utf-8")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            result = load(config_path, _FERNET_KEY)
        assert result == {}

    def test_load_bad_encryption_skips_field(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        raw = {"smtp_password": "not-a-fernet-token", "smtp_host": "mail.example.com"}  # NOSONAR
        (tmp_path / "weftmark_config.json").write_text(json.dumps(raw), encoding="utf-8")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            result = load(config_path, _FERNET_KEY)
        # Bad token is skipped; plain field is preserved
        assert "smtp_password" not in result
        assert result["smtp_host"] == "mail.example.com"

    def test_load_secret_field_decrypted(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        token = encrypt("s3cr3t", _FERNET_KEY)
        raw = {"smtp_password": token}
        (tmp_path / "weftmark_config.json").write_text(json.dumps(raw), encoding="utf-8")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            result = load(config_path, _FERNET_KEY)
        assert result["smtp_password"] == "s3cr3t"


# ---------------------------------------------------------------------------
# save — edge cases
# ---------------------------------------------------------------------------


class TestSaveEdgeCases:
    def test_save_secret_field_is_encrypted_at_rest(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _FERNET_KEY, {"smtp_password": "hunter2"})  # NOSONAR
        raw = json.loads((tmp_path / "weftmark_config.json").read_text())
        assert raw["smtp_password"] != "hunter2"
        assert decrypt(raw["smtp_password"], _FERNET_KEY) == "hunter2"

    def test_save_merges_with_corrupt_existing_file(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        (tmp_path / "weftmark_config.json").write_text("CORRUPT", encoding="utf-8")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path}):
            save(config_path, _FERNET_KEY, {"smtp_host": "new-host"})
            result = load(config_path, _FERNET_KEY)
        assert result["smtp_host"] == "new-host"


# ---------------------------------------------------------------------------
# sync_env_to_file
# ---------------------------------------------------------------------------


class TestSyncEnvToFile:
    def test_no_env_fields_is_noop(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch("app.services.config_file.env_source_fields", return_value={}):
            sync_env_to_file(config_path, _FERNET_KEY)
        assert not (tmp_path / "weftmark_config.json").exists()

    def test_env_field_synced_to_file(self, tmp_path):
        config_path = str(tmp_path / "weftmark_config.json")
        with patch.dict(os.environ, {"CONFIG_FILE_PATH": config_path, "SMTP_HOST": "env-smtp.example.com"}):
            sync_env_to_file(config_path, _FERNET_KEY)
            result = load(config_path, _FERNET_KEY)
        assert result.get("smtp_host") == "env-smtp.example.com"
