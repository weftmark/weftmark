"""Unit tests for Settings field validators and config_warnings()."""

from __future__ import annotations

import pytest

from app.config import Settings


def _s(**kwargs) -> Settings:
    """Build a Settings with test-safe defaults, overriding with kwargs.

    All S3 vars are explicitly cleared so ambient container env vars don't
    bleed into tests that check for missing-S3 warnings.
    """
    defaults = {
        "app_env": "dev",
        "debug": True,
        "clerk_webhook_secret": "whsec_test123",
        "cors_origins": "http://localhost:3000",
        "storage_backend": "local",
        "log_level": "INFO",
        # Explicitly clear S3 vars so container env doesn't pollute tests
        "s3_endpoint_url": "",
        "s3_access_key_id": "",
        "s3_secret_access_key": "",
        "s3_bucket_name": "",
        "s3_region": "",
    }
    return Settings(**{**defaults, **kwargs})


class TestLogLevelValidator:
    def test_valid_levels_accepted(self):
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            s = _s(log_level=level)
            assert s.log_level == level

    def test_lowercase_normalised_to_upper(self):
        assert _s(log_level="info").log_level == "INFO"
        assert _s(log_level="debug").log_level == "DEBUG"
        assert _s(log_level="warning").log_level == "WARNING"

    def test_mixed_case_normalised(self):
        assert _s(log_level="Warning").log_level == "WARNING"

    def test_invalid_level_raises_with_message(self):
        with pytest.raises(Exception, match="LOG_LEVEL"):
            _s(log_level="VERBOSE")

    def test_numeric_string_raises(self):
        with pytest.raises(Exception, match="LOG_LEVEL"):
            _s(log_level="3")

    def test_empty_string_raises(self):
        with pytest.raises(Exception, match="LOG_LEVEL"):
            _s(log_level="")


class TestStorageBackendValidator:
    def test_local_accepted(self):
        assert _s(storage_backend="local").storage_backend == "local"

    def test_s3_accepted(self):
        assert _s(storage_backend="s3").storage_backend == "s3"

    def test_uppercase_normalised_to_lower(self):
        assert _s(storage_backend="LOCAL").storage_backend == "local"
        assert _s(storage_backend="S3").storage_backend == "s3"

    def test_invalid_backend_raises_with_message(self):
        with pytest.raises(Exception, match="STORAGE_BACKEND"):
            _s(storage_backend="gcs")

    def test_azure_raises(self):
        with pytest.raises(Exception, match="STORAGE_BACKEND"):
            _s(storage_backend="azure")

    def test_empty_string_raises(self):
        with pytest.raises(Exception, match="STORAGE_BACKEND"):
            _s(storage_backend="")


class TestConfigWarnings:
    def test_no_warnings_with_clean_local_config(self):
        assert _s().config_warnings() == []

    def test_no_warnings_with_full_s3_config(self):
        s = _s(
            storage_backend="s3",
            s3_endpoint_url="https://s3.example.com",
            s3_access_key_id="AKIDTEST",
            s3_secret_access_key="secretvalue",
            s3_bucket_name="my-bucket",
        )
        assert s.config_warnings() == []

    def test_s3_backend_all_vars_missing_warns(self):
        s = _s(storage_backend="s3")
        warnings = s.config_warnings()
        assert len(warnings) >= 1
        assert any("S3" in w for w in warnings)

    def test_s3_backend_partial_vars_warns(self):
        s = _s(storage_backend="s3", s3_bucket_name="bucket")
        warnings = s.config_warnings()
        combined = " ".join(warnings)
        assert "S3_ACCESS_KEY_ID" in combined or "S3_SECRET_ACCESS_KEY" in combined

    def test_s3_backend_only_endpoint_set_warns(self):
        s = _s(storage_backend="s3", s3_endpoint_url="https://r2.example.com")
        warnings = s.config_warnings()
        assert any("S3" in w for w in warnings)

    def test_local_backend_unused_s3_vars_no_warning(self):
        s = _s(
            storage_backend="local",
            s3_endpoint_url="https://s3.example.com",
            s3_access_key_id="KEY",
            s3_secret_access_key="secret",
            s3_bucket_name="bucket",
        )
        assert s.config_warnings() == []

    def test_cors_with_space_after_comma_warns(self):
        s = _s(cors_origins="http://localhost:3000, http://localhost:3001")
        warnings = s.config_warnings()
        assert any("CORS_ORIGINS" in w for w in warnings)

    def test_cors_with_leading_space_warns(self):
        s = _s(cors_origins=" http://localhost:3000")
        warnings = s.config_warnings()
        assert any("CORS_ORIGINS" in w for w in warnings)

    def test_cors_without_spaces_no_warning(self):
        s = _s(cors_origins="http://localhost:3000,http://localhost:3001")
        assert s.config_warnings() == []

    def test_cors_single_origin_no_warning(self):
        s = _s(cors_origins="https://example.com")
        assert s.config_warnings() == []

    def test_missing_webhook_secret_warns(self):
        s = _s(clerk_webhook_secret="")
        warnings = s.config_warnings()
        assert any("CLERK_WEBHOOK_SECRET" in w for w in warnings)

    def test_malformed_webhook_secret_warns(self):
        s = _s(clerk_webhook_secret="notawhsec_format")
        warnings = s.config_warnings()
        assert any("CLERK_WEBHOOK_SECRET" in w for w in warnings)

    def test_valid_webhook_secret_no_warning(self):
        s = _s(clerk_webhook_secret="whsec_abcdef1234567890")
        assert s.config_warnings() == []

    def test_multiple_issues_all_reported(self):
        s = _s(
            storage_backend="s3",
            cors_origins="http://a.com, http://b.com",
            clerk_webhook_secret="",
        )
        warnings = s.config_warnings()
        assert len(warnings) >= 3
